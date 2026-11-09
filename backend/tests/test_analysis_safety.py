"""P4 synthetic regressions. Signing doubles are confined to tests."""

import base64
import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import DatabaseError, transaction
from django.utils import timezone
from test_analysis import scenario as analysis_scenario  # noqa: F401
from test_analysis import sign_opinion, signature_identity
from test_identity import approve, signed, user

from identity.analysis import decode
from identity.analysis_pipeline import PIPELINE, QWEN_SHA256, extract, suggested_text
from identity.analysis_registry import current_policy, manifest
from identity.analysis_signing import VerifiedClinicalSignature
from identity.models import (
    AnalysisDraft,
    AnalysisIncident,
    AnalysisJob,
    AnalysisOpinion,
    AnalysisPolicyEvent,
    AnalysisReviewSession,
    AnalysisSignature,
    AuditEvent,
    Membership,
)
from identity.tasks import run_clinical_analysis

pytestmark = pytest.mark.django_db


@pytest.fixture
def scenario(analysis_scenario):  # noqa: F811
    return analysis_scenario


def policy(author, record, enabled=True, digest=None):
    return AnalysisPolicyEvent.objects.create(
        organization=record.organization,
        author=author,
        enabled=enabled,
        manifest_hash=digest or manifest()[1],
        reason="SYNTHETIC test decision",
    )


@pytest.fixture
def ready(scenario):
    author, person, record, version = scenario
    browser = signed(author)
    job = browser.post(f"clinical/versions/{version.pk}/analysis/", {}).data["id"]
    with (
        patch(
            "identity.analysis_pipeline.pages_from",
            return_value=[
                (
                    "Glucosio 110 mg/dL 60-100",
                    "embedded",
                    None,
                    [{"bbox": [10, 20, 100, 30], "coordinate_system": "pdf_points_top_left"}],
                )
            ],
        ),
        patch(
            "identity.analysis_pipeline.summary",
            return_value={"rows": ["1:1"], "checksum": QWEN_SHA256},
        ),
    ):
        run_clinical_analysis(job)
    path = f"clinical/analysis/{job}/"
    return author, person, record, version, browser, path


def reviewed(ready):
    author, person, record, version, browser, path = ready
    assert browser.post(path + "review-start/", {}).status_code == 200
    response = browser.post(
        path + "review/",
        {
            "decision": "modify",
            "text": "SYNTHETIC final opinion",
            "confirmed": True,
            "source_checked": True,
            "confirmed_rows": ["1:1"],
        },
    )
    assert response.status_code == 201, response.content
    detail = browser.get(path).data["opinion"]
    assert hashlib.sha256(detail["signing_content"].encode()).hexdigest() == detail["digest"]
    assert json.loads(detail["signing_content"])["text"] == "SYNTHETIC final opinion"
    return response.data["opinion"]


def test_registry_permissions_approval_hash_and_immutable_events(scenario):
    author, person, record, version = scenario
    browser = signed(author)
    path = f"organizations/{record.organization_id}/analysis/registry/"
    assert signed(person).get(path).status_code == 403
    Membership.objects.filter(user=author, organization=record.organization).update(
        role="professional"
    )
    assert browser.get(path).status_code == 404
    Membership.objects.filter(user=author, organization=record.organization).update(role="admin")
    registry = browser.get(path)
    assert registry.status_code == 200 and registry.data["manifest"]["pipeline"] == PIPELINE
    body = {"enabled": False, "manifest_hash": manifest()[1], "reason": "SYNTHETIC kill-switch"}
    assert browser.post(path, {**body, "manifest_hash": "0" * 64}).status_code == 404
    response = browser.post(path, body)
    assert response.status_code == 201
    event = AnalysisPolicyEvent.objects.get(pk=response.data["id"])
    for mutation in (
        lambda: AnalysisPolicyEvent.objects.filter(pk=event.pk).update(enabled=True),
        lambda: AnalysisPolicyEvent.objects.filter(pk=event.pk).delete(),
    ):
        with pytest.raises(DatabaseError), transaction.atomic():
            mutation()
    assert browser.post(f"clinical/versions/{version.pk}/analysis/", {}).status_code == 403
    assert browser.post(path, {**body, "enabled": True}).status_code == 201
    assert browser.post(f"clinical/versions/{version.pk}/analysis/", {}).status_code == 202
    assert AuditEvent.objects.filter(action="analysis.registry_disabled", actor=author).exists()
    assert AuditEvent.objects.filter(action="analysis.registry_read", actor=author).exists()


def test_stale_registry_and_no_policy_deny_execution(scenario):
    author, _, record, version = scenario
    browser = signed(author)
    policy(author, record, digest="0" * 64)
    assert current_policy(record.organization_id) is None
    assert browser.post(f"clinical/versions/{version.pk}/analysis/", {}).status_code == 403
    # A manifest update also invalidates the previous approval without changing its history.
    policy(author, record)
    with patch("identity.analysis_registry.manifest", return_value=({}, "f" * 64)):
        assert browser.post(f"clinical/versions/{version.pk}/analysis/", {}).status_code == 403


def test_kill_switch_during_worker_discards_output(scenario):
    author, _, record, version = scenario
    browser = signed(author)
    job = browser.post(f"clinical/versions/{version.pk}/analysis/", {}).data["id"]

    def stop(*args):
        policy(author, record, False)
        return [("Glucosio 110 mg/dL 60-100", "embedded")]

    with (
        patch("identity.analysis_pipeline.pages_from", side_effect=stop),
        patch("identity.analysis_pipeline.summary", return_value=None),
    ):
        run_clinical_analysis(job)
    assert AnalysisJob.objects.get(pk=job).state == "cancelled"
    assert not AnalysisDraft.objects.exists()
    assert browser.get(f"clinical/analysis/{job}/").status_code == 404
    policy(author, record, True)
    assert browser.get(f"clinical/analysis/{job}/").status_code == 404
    assert browser.post(f"clinical/versions/{version.pk}/analysis/", {}).data["id"] != job


def test_unpinned_summary_model_cannot_create_draft(scenario):
    author, _, _, version = scenario
    job = signed(author).post(f"clinical/versions/{version.pk}/analysis/", {}).data["id"]
    with (
        patch(
            "identity.analysis_pipeline.pages_from",
            return_value=[("Glucosio 110 mg/dL 60-100", "embedded")],
        ),
        patch(
            "identity.analysis_pipeline.summary",
            return_value={"rows": ["1:1"], "checksum": "0" * 64},
        ),
    ):
        for _ in range(3):
            run_clinical_analysis(job)
    assert AnalysisJob.objects.get(pk=job).state == "failed"
    assert not AnalysisDraft.objects.exists()


@pytest.mark.parametrize("missing", ["session", "source", "rows", "unknown", "duplicate"])
def test_uncertain_evidence_requires_explicit_confirmation(ready, missing):
    _, _, _, _, browser, path = ready
    body = {
        "decision": "modify",
        "text": "SYNTHETIC",
        "confirmed": True,
        "source_checked": True,
        "confirmed_rows": ["1:1"],
    }
    if missing != "session":
        browser.post(path + "review-start/", {})
    if missing == "source":
        body["source_checked"] = False
    if missing == "rows":
        body["confirmed_rows"] = []
    if missing == "unknown":
        body["confirmed_rows"] = ["1:1", "99:1"]
    if missing == "duplicate":
        body["confirmed_rows"] = ["1:1", "1:1"]
    assert browser.post(path + "review/", body).status_code == 400
    assert not AnalysisOpinion.objects.exists()


def test_empty_or_truncated_extraction_cannot_be_attested(scenario):
    author, _, _, version = scenario
    browser = signed(author)
    job = browser.post(f"clinical/versions/{version.pk}/analysis/", {}).data["id"]
    with patch(
        "identity.analysis_pipeline.pages_from", return_value=[("123\n" * 1001, "embedded")]
    ):
        run_clinical_analysis(job)
    path = f"clinical/analysis/{job}/"
    browser.post(path + "review-start/", {})
    assert (
        browser.post(
            path + "review/",
            {
                "decision": "modify",
                "text": "SYNTHETIC",
                "confirmed": True,
                "source_checked": True,
                "confirmed_rows": [row["id"] for row in browser.get(path).data["draft"]["rows"]],
            },
        ).status_code
        == 400
    )
    assert (
        browser.post(
            path + "review/", {"decision": "reject", "text": "Incomplete source"}
        ).status_code
        == 201
    )


def test_signature_unavailable_and_no_unsigned_publication(ready, settings):
    _, person, record, _, browser, _ = ready
    opinion = reviewed(ready)
    settings.CLINICAL_SIGNATURE_VERIFIER = ""
    assert (
        browser.post(
            f"clinical/opinions/{opinion}/sign/",
            {
                "artifact": base64.b64encode(b"synthetic").decode(),
                **signature_identity(
                    AnalysisOpinion.objects.get(pk=opinion).review.job.version.document.patient
                ),
            },
        ).status_code
        == 503
    )
    assert browser.post(f"clinical/opinions/{opinion}/publish/", {}).status_code == 409
    assert signed(person).get(f"clinical/patients/{record.pk}/opinions/").data["count"] == 0


@pytest.mark.parametrize(
    "fault", ["digest", "signer", "future", "naive", "format", "provider", "long_provider"]
)
def test_signature_must_bind_signer_digest_and_time(ready, fault):
    author, person, _, _, browser, _ = ready
    opinion = reviewed(ready)
    proof = VerifiedClinicalSignature(
        author.pk,
        AnalysisOpinion.objects.get(pk=opinion).attestation_hash,
        timezone.now(),
        "SYNTHETIC",
        "CAdES",
    )
    changes = {
        "digest": {"digest": "0" * 64},
        "signer": {"signer_id": person.pk},
        "future": {"signed_at": timezone.now() + timedelta(days=1)},
        "naive": {"signed_at": timezone.now().replace(tzinfo=None)},
        "format": {"format": "plain"},
        "provider": {"provider_reference": ""},
        "long_provider": {"provider_reference": "x" * 161},
    }
    with patch("identity.analysis_views.verifier") as adapter:
        adapter.return_value.verify.return_value = replace(proof, **changes[fault])
        response = browser.post(
            f"clinical/opinions/{opinion}/sign/",
            {
                "artifact": base64.b64encode(b"synthetic").decode(),
                **signature_identity(
                    AnalysisOpinion.objects.get(pk=opinion).review.job.version.document.patient
                ),
            },
        )
    assert response.status_code == 400
    assert not AnalysisSignature.objects.exists()


def test_signed_opinion_hidden_after_kill_and_not_resurrected(ready):
    author, person, record, version, browser, path = ready
    opinion = reviewed(ready)
    sign_opinion(browser, author, opinion)
    assert browser.post(f"clinical/opinions/{opinion}/publish/", {}).status_code == 204
    patient = signed(person)
    published = f"clinical/patients/{record.pk}/opinions/"
    assert patient.get(published).data["count"] == 1
    policy(author, record, False)
    assert patient.get(published).data["count"] == 0
    assert browser.get(path).status_code == 404
    for endpoint in (f"clinical/opinions/{opinion}/publish/", f"clinical/opinions/{opinion}/sign/"):
        assert (
            browser.post(
                endpoint, {"artifact": "c3ludGhldGlj", **signature_identity(record)}
            ).status_code
            == 404
        )
    policy(author, record)
    assert patient.get(published).data["count"] == 0
    assert browser.post(f"clinical/versions/{version.pk}/analysis/", {}).status_code == 202


def test_kill_during_signature_verification_cannot_commit(ready):
    author, _, record, _, browser, _ = ready
    opinion = reviewed(ready)

    def stop(**kwargs):
        policy(author, record, False)
        return VerifiedClinicalSignature(
            author.pk, kwargs["expected_digest"], timezone.now(), "SYNTHETIC", "PAdES"
        )

    with patch("identity.analysis_views.verifier") as adapter:
        adapter.return_value.verify.side_effect = stop
        assert (
            browser.post(
                f"clinical/opinions/{opinion}/sign/",
                {"artifact": "c3ludGhldGlj", **signature_identity(record)},
            ).status_code
            == 404
        )
    assert not AnalysisSignature.objects.exists()


def test_incident_encryption_metrics_and_immutable_sessions(ready):
    author, _, record, _, browser, path = ready
    response = browser.post(
        path + "incidents/", {"category": "missed_finding", "note": "SYNTHETIC adverse event"}
    )
    assert response.status_code == 201
    incident = AnalysisIncident.objects.get()
    assert b"adverse event" not in bytes(incident.ciphertext)
    assert decode(incident, incident.job.version.document)["note"] == "SYNTHETIC adverse event"
    reviewed(ready)
    for model, values in (
        (AnalysisIncident, {"category": "other"}),
        (AnalysisReviewSession, {"created_at": timezone.now()}),
    ):
        with pytest.raises(DatabaseError), transaction.atomic():
            model.objects.update(**values)
    Membership.objects.filter(user=author, organization=record.organization).update(role="admin")
    metrics = browser.get(f"organizations/{record.organization_id}/analysis/metrics/")
    assert metrics.status_code == 200
    row = metrics.data[0]
    assert row["average_review_duration"] >= 0
    assert row["average_extracted_rows"] == row["average_uncertain_rows"] == 1
    assert row["modify_rate"] == 1 and row["reject_rate"] == 0
    assert AuditEvent.objects.filter(action="analysis.metrics_read", actor=author).exists()


@pytest.mark.parametrize("endpoint", ["review-start/", "incidents/", "review/"])
def test_new_job_endpoints_deny_patient_and_other_tenant(ready, endpoint):
    _, person, _, _, _, path = ready
    outsider = user("p4-outsider@patients.example", "professional")
    approve(outsider)
    body = {"category": "other", "note": "SYNTHETIC", "decision": "reject", "text": "SYNTHETIC"}
    assert signed(person).post(path + endpoint, body).status_code == 403
    assert signed(outsider).post(path + endpoint, body).status_code == 404


@pytest.mark.parametrize("refs", [["unknown"], ["1:1", "1:1"], [], [["1:1"]], "1:1", ["1:1"] * 6])
def test_summary_rejects_invented_and_malformed_references(refs):
    rows = extract([("Glucosio 110 mg/dL 60-100", "embedded")])
    assert (
        suggested_text({"rows": rows, "summary": {"rows": refs, "text": "invented diagnosis 999"}})
        == ""
    )


def test_summary_renders_only_structured_values_and_ucum():
    rows = extract([("Creatinina 80 μmol/L 50-100", "embedded")])
    assert rows[0]["loinc"] == "14682-9" and rows[0]["ucum"] == "umol/L"
    rendered = suggested_text({"rows": rows, "summary": {"rows": ["1:1"], "text": "diagnosis 999"}})
    assert "80 µmol/L" in rendered and "999" not in rendered and "diagnosis" not in rendered


def test_signature_checks_patient_and_rejects_invalid_base64(ready):
    _, _, record, _, browser, _ = ready
    opinion = reviewed(ready)
    path = f"clinical/opinions/{opinion}/sign/"
    body = {"artifact": "c3ludGhldGlj", **signature_identity(record)}
    with patch("identity.analysis_views.verifier") as adapter:
        assert browser.post(path, {**body, "identifier_value": "WRONG-PATIENT"}).status_code == 400
        assert browser.post(path, {**body, "source_birth_date": "1901-01-01"}).status_code == 400
        assert browser.post(path, {**body, "artifact": "not-base64"}).status_code == 400
        assert browser.post(path, {**body, "artifact": ""}).status_code == 400
        adapter.assert_not_called()


def test_signature_and_incident_payloads_are_erased_only_after_purge(ready):
    from identity.clinical_storage import maintain_version

    author, _, _, version, browser, path = ready
    opinion = reviewed(ready)
    sign_opinion(browser, author, opinion)
    assert (
        browser.post(path + "incidents/", {"category": "other", "note": "SYNTHETIC"}).status_code
        == 201
    )
    for model in (AnalysisSignature, AnalysisIncident):
        with pytest.raises(DatabaseError), transaction.atomic():
            model.objects.update(ciphertext=b"", wrapped_key=b"")
    version.document.deleted_at = timezone.now() - timedelta(days=2)
    version.document.save(update_fields=["deleted_at"])
    with patch("identity.clinical_storage.delete_object"):
        maintain_version(version.pk, cutoff=timezone.now() - timedelta(days=1))
    for model in (AnalysisSignature, AnalysisIncident):
        assert not bytes(model.objects.get().ciphertext)
        assert not bytes(model.objects.get().wrapped_key)


def test_global_switch_hides_previously_published_opinion(ready, settings):
    author, person, record, _, browser, _ = ready
    opinion = reviewed(ready)
    sign_opinion(browser, author, opinion)
    assert browser.post(f"clinical/opinions/{opinion}/publish/", {}).status_code == 204
    settings.CLINICAL_ANALYSIS_ENABLED = False
    assert signed(person).get(f"clinical/patients/{record.pk}/opinions/").data["count"] == 0
    assert browser.post(f"clinical/opinions/{opinion}/publish/", {}).status_code == 403


def test_configured_signature_adapter_is_loaded_explicitly(settings):
    from identity.analysis_signing import verifier

    settings.CLINICAL_SIGNATURE_VERIFIER = "synthetic.test.only.Verifier"
    with patch("identity.analysis_signing.import_string") as loader:
        assert verifier() == loader.return_value.return_value
        loader.assert_called_once_with(settings.CLINICAL_SIGNATURE_VERIFIER)


def test_analysis_population_and_access_policy_fail_closed(scenario, settings):
    from identity.analysis import authorized_jobs

    author, person, record, version = scenario
    browser = signed(author)
    assert not authorized_jobs(person).exists()
    record.birth_date = timezone.localdate()
    record.save(update_fields=["birth_date"])
    assert browser.post(f"clinical/versions/{version.pk}/analysis/", {}).status_code == 404
    settings.CLINICAL_ANALYSIS_ENABLED = False
    assert not authorized_jobs(author).exists()


def test_signature_endpoint_denies_patient_and_other_tenant(ready):
    _, person, _, _, _, _ = ready
    opinion = reviewed(ready)
    outsider = user("p4-sign-outsider@patients.example", "professional")
    approve(outsider)
    path = f"clinical/opinions/{opinion}/sign/"
    assert signed(person).post(path, {"artifact": "c3ludGhldGlj"}).status_code == 403
    assert signed(outsider).post(path, {"artifact": "c3ludGhldGlj"}).status_code == 404
