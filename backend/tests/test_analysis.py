from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.db import DatabaseError, transaction
from test_clinical import PDF
from test_identity import approve, org_for, patient, signed, user

from identity.analysis_pipeline import DISCLAIMER, extract
from identity.clinical import seal
from identity.models import (
    AnalysisDraft,
    AnalysisJob,
    AnalysisOpinion,
    AuditEvent,
    CareRelationship,
    ClinicalDocument,
    ClinicalDocumentVersion,
)
from identity.tasks import run_clinical_analysis

pytestmark = pytest.mark.django_db


@pytest.fixture
def scenario(settings):
    settings.CLINICAL_ANALYSIS_ENABLED = True
    settings.CLINICAL_MASTER_KEY = Fernet.generate_key().decode()
    author = user("lab-author@patients.example", "professional")
    approve(author)
    person = user("lab-patient@patients.example")
    record = patient(org_for(author), author)
    record.account = person
    record.save(update_fields=["account"])
    document = ClinicalDocument.objects.create(patient=record, author=author, kind="report")
    version = ClinicalDocumentVersion.objects.create(
        document=document,
        number=1,
        title="Synthetic",
        media_type="application/pdf",
        size=len(PDF),
        **seal(PDF, record.organization_id),
    )
    return author, person, record, version


@pytest.mark.parametrize("decision", ["accept", "modify"])
def test_analysis_review_publication_and_tenant_isolation(scenario, decision):
    author, person, record, version = scenario
    reviewer, patient_browser = signed(author), signed(person)
    outsider = user("lab-outsider@patients.example", "professional")
    approve(outsider)
    outside = signed(outsider)
    start = f"clinical/versions/{version.pk}/analysis/"
    assert outside.post(start, {}).status_code == 404
    assert patient_browser.post(start, {}).status_code == 403
    first = reviewer.post(start, {})
    assert first.status_code == 202, first.content
    assert reviewer.post(start, {}).data["id"] == first.data["id"]
    job_id = first.data["id"]
    assert patient_browser.get(start).status_code == 403
    assert outside.get(start).data["count"] == 0
    assert reviewer.get(start).data["count"] == 1
    assert AuditEvent.objects.filter(
        actor=author, action="analysis.job_listed", resource_id=job_id
    ).exists()
    path = f"clinical/analysis/{job_id}/"
    published = f"clinical/patients/{record.pk}/opinions/"
    assert patient_browser.get(path).status_code == 403
    assert outside.get(path).status_code == 404
    with (
        patch(
            "identity.analysis_pipeline.pages_from",
            return_value=[("Glucosio 110 mg/dL 60–100", "embedded")],
        ),
        patch(
            "identity.analysis_pipeline.summary",
            return_value={"rows": ["1:1"], "checksum": "0" * 64} if decision == "accept" else None,
        ),
    ):
        run_clinical_analysis(job_id)
        run_clinical_analysis(job_id)
    assert AnalysisDraft.objects.count() == 1
    assert b"glucosio" not in bytes(AnalysisDraft.objects.get().ciphertext)
    detail = reviewer.get(path).data
    assert detail["disclaimer"] == DISCLAIMER
    assert detail["draft"]["rows"][0]["flag"] == "above"
    assert patient_browser.get(published).data["count"] == 0
    text = detail["suggestion"] if decision == "accept" else "Parere sintetico verificato"
    body = {"decision": decision, "text": text, "confirmed": True}
    if decision == "accept":
        assert reviewer.post(path + "review/", {**body, "text": "Testo diverso"}).status_code == 400
    assert reviewer.post(path + "review/", {**body, "confirmed": False}).status_code == 400
    reviewed = reviewer.post(path + "review/", body)
    assert reviewed.status_code == 201, reviewed.content
    assert reviewer.post(path + "review/", body).status_code == 409
    with pytest.raises(DatabaseError), transaction.atomic():
        AnalysisOpinion.objects.filter(pk=reviewed.data["opinion"]).update(attestation_hash="bad")
    assert patient_browser.get(published).data["count"] == 0
    publish = f"clinical/opinions/{reviewed.data['opinion']}/publish/"
    assert outside.post(publish, {}).status_code == 404
    assert reviewer.post(publish, {}).status_code == 204
    response = patient_browser.get(published).data["results"]
    assert response[0]["text"] == body["text"]
    assert "draft" not in response[0] and "decision" not in response[0]


def test_analysis_revoked_during_run_and_retry(scenario):
    author, _, record, version = scenario
    reviewer = signed(author)
    job_id = reviewer.post(f"clinical/versions/{version.pk}/analysis/", {}).data["id"]
    with patch("identity.analysis_pipeline.pages_from", side_effect=OSError):
        run_clinical_analysis(job_id)
    assert AnalysisJob.objects.get(pk=job_id).state == "queued"

    def revoke(*args):
        CareRelationship.objects.filter(patient=record, professional=author).update(active=False)
        return [("Glucosio 85 mg/dL 60–100", "embedded")]

    with patch("identity.analysis_pipeline.pages_from", side_effect=revoke):
        run_clinical_analysis(job_id)
    job = AnalysisJob.objects.get(pk=job_id)
    assert job.state == "cancelled" and job.attempts == 2
    assert not AnalysisDraft.objects.exists()


@pytest.mark.parametrize(
    ("line", "flag", "expected"),
    [
        ("Glucosio 110 mg/dL 60-100", "above", "110"),
        ("Glucosio <60 mg/dL 60-100", "below", "60"),
        ("Glucosio >100 mg/dL 60-100", "above", "100"),
        ("Glucosio >80 mg/dL 60-100", "ambiguous", "80"),
        ("Creatinina 0,95 mg/dL 0,50–1,20", "within", "0.95"),
        ("Creatinina 0,95 g/dL 0,50–1,20", "unit_mismatch", "0.95"),
        ("Emoglobina 12 g/dL", "missing_range", "12"),
        ("Colesterolo illeggibile", "ambiguous", None),
    ],
)
def test_golden_report_rows(line, flag, expected):
    (row,) = extract([(line, "embedded")])
    assert row["flag"] == flag and row.get("value") == expected


@pytest.mark.django_db(transaction=True)
def test_concurrent_rejections_can_only_record_one_review(scenario):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections
    from rest_framework.test import APIClient

    from identity.models import AnalysisReview

    author, person, record, version = scenario
    reviewer = signed(author)
    patient_browser = signed(person)
    job_id = reviewer.post(f"clinical/versions/{version.pk}/analysis/", {}).data["id"]
    with patch(
        "identity.analysis_pipeline.pages_from",
        return_value=[("Glucosio 110 mg/dL 60-100", "embedded")],
    ):
        run_clinical_analysis(job_id)
    path = f"/api/v1/clinical/analysis/{job_id}/review/"
    cookies = {key: value.value for key, value in reviewer.client.cookies.items()}
    barrier = Barrier(2)

    def submit(text):
        close_old_connections()
        try:
            client = APIClient(enforce_csrf_checks=True)
            for key, value in cookies.items():
                client.cookies[key] = value
            barrier.wait(timeout=5)
            return client.post(
                path,
                {"decision": "reject", "text": text},
                format="json",
                HTTP_X_CSRFTOKEN=cookies["csrftoken"],
            ).status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(submit, ["First reason", "Second reason"])) == [201, 409]
    assert AnalysisReview.objects.get(job_id=job_id).decision == "reject"
    assert not AnalysisOpinion.objects.filter(review__job_id=job_id).exists()
    assert patient_browser.get(f"clinical/patients/{record.pk}/opinions/").data["count"] == 0


def test_extraction_reports_limits():
    notices: set[str] = set()
    rows = extract([("123\n" * 1001, "embedded")], notices=notices)
    assert len(rows) == 100
    assert notices == {"page_line_limit", "evidence_limit"}


def test_source_purge_erases_analysis_payloads(scenario):
    from datetime import timedelta

    from django.utils import timezone

    from identity.clinical_storage import maintain_version
    from identity.models import AnalysisReview

    author, _, _, version = scenario
    reviewer = signed(author)
    job_id = reviewer.post(f"clinical/versions/{version.pk}/analysis/", {}).data["id"]
    run_clinical_analysis(job_id)
    response = reviewer.post(
        f"clinical/analysis/{job_id}/review/",
        {
            "decision": "modify",
            "text": "Synthetic opinion",
            "confirmed": True,
        },
    )
    assert response.status_code == 201
    opinion = AnalysisOpinion.objects.get()
    attestation = opinion.attestation_hash
    document = version.document
    document.deleted_at = timezone.now() - timedelta(days=2)
    document.save(update_fields=["deleted_at"])
    with patch("identity.clinical_storage.delete_object"):
        maintain_version(version.pk, cutoff=timezone.now() - timedelta(days=1))
    for row in (
        AnalysisDraft.objects.get(),
        AnalysisReview.objects.get(),
        AnalysisOpinion.objects.get(),
    ):
        assert not bytes(row.ciphertext) and not bytes(row.wrapped_key)
    assert AnalysisOpinion.objects.get().attestation_hash == attestation


def test_failed_offload_leaves_next_document_eligible(scenario):
    from identity.clinical import DocumentUnavailable
    from identity.tasks import offload_clinical_version, reconcile_clinical_storage

    _, _, _, version = scenario
    next_version = ClinicalDocumentVersion.objects.create(
        document=version.document,
        number=2,
        title="Next",
        media_type=version.media_type,
        size=0,
        sha256="",
        ciphertext=b"",
        wrapped_key=b"",
    )
    with patch("identity.tasks.offload", side_effect=DocumentUnavailable):
        offload_clinical_version(str(version.pk))
    with patch("identity.tasks.offload_clinical_version.delay") as dispatch:
        reconcile_clinical_storage()
        dispatch.assert_called_once_with(str(next_version.pk))
