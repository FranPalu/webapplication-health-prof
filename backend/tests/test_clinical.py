from io import BytesIO
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.core.files.uploadedfile import SimpleUploadedFile
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from test_identity import approve, org_for, patient, signed, user

from identity.models import (
    AuditEvent,
    CareRelationship,
    ClinicalDocumentVersion,
    ConsentTextVersion,
    PatientConsent,
    Share,
)

pytestmark = pytest.mark.django_db


def synthetic_pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 20 Td (KeywordSaffron) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    result = BytesIO()
    writer.write(result)
    return result.getvalue()


PDF = synthetic_pdf()


def test_clinical_version_lifecycle_and_access(settings, monkeypatch):
    monkeypatch.setenv("CLINICAL_SEARCH_KEY", Fernet.generate_key().decode())
    settings.CLINICAL_MASTER_KEY = Fernet.generate_key().decode()
    professional = user("document-author@patients.example", "professional")
    approve(professional)
    author = signed(professional)
    patient_account = user("document-patient@patients.example")
    patient_browser = signed(patient_account)
    record = patient(org_for(professional), professional)
    record.account = patient_account
    record.save(update_fields=["account"])
    outsider = signed(user("document-outsider@patients.example"))
    url = f"clinical/patients/{record.pk}/documents/"
    csrf = {"HTTP_X_CSRFTOKEN": author.client.cookies["csrftoken"].value}

    def upload(path, content=PDF, **extra):
        return author.client.post(
            "/api/v1/" + path,
            {
                "file": SimpleUploadedFile("test.pdf", content, content_type="application/pdf"),
                "title": "Synthetic report",
                **extra,
            },
            format="multipart",
            **csrf,
        )

    with patch.dict("os.environ", {"CLINICAL_CLAMAV_HOST": ""}):
        assert upload(url).status_code == 503
    assert ClinicalDocumentVersion.objects.count() == 0
    with patch("identity.clinical.scan") as scanner:
        assert upload(url, b"not a PDF").status_code == 400
        scanner.assert_not_called()
        created = upload(url)
        assert created.status_code == 201, created.content
        scanner.assert_called_once_with(PDF)
        doc = f"clinical/documents/{created.data['document']}/"
        newer = upload(doc)
        assert newer.status_code == 201, newer.content
        assert newer.data["number"] == 2
        private = upload(url, kind="psychology")
        assert private.status_code == 201

    version = ClinicalDocumentVersion.objects.get(pk=created.data["id"])
    assert PDF not in bytes(version.ciphertext)
    download = f"clinical/versions/{version.pk}/download/"
    fhir = f"fhir/DocumentReference/{version.pk}"
    assert patient_browser.get(download).content == PDF
    assert patient_browser.get(fhir).json()["status"] == "superseded"
    fhir_patient = f"fhir/Patient/{record.pk}"
    assert patient_browser.get(fhir_patient).json()["resourceType"] == "Patient"
    assert outsider.get(fhir_patient).status_code == 404
    types = patient_browser.get("fhir/metadata").json()["rest"][0]["resource"]
    assert {resource["type"] for resource in types} == {
        "Patient",
        "DocumentReference",
        "Organization",
        "Practitioner",
        "Consent",
        "Encounter",
        "DiagnosticReport",
        "Observation",
        "Provenance",
    }
    assert outsider.get(download).status_code == 404
    assert outsider.get(fhir).status_code == 404
    assert outsider.get(url + "?q=Synthetic").data["count"] == 0
    assert patient_browser.get(url + "?q=Synthetic").data["count"] == 1
    assert author.get(url + "?q=Synthetic").data["count"] == 2
    assert patient_browser.get(url + "?q=KeywordSaffron").data["count"] == 1
    assert outsider.get(url + "?q=KeywordSaffron").data["count"] == 0
    assert patient_browser.get(f"fhir/DocumentReference/{private.data['id']}").status_code == 404
    recipient = user("document-recipient@patients.example", "professional")
    approve(recipient)
    recipient_browser = signed(recipient)
    share = Share.objects.create(
        patient=record,
        granted_by=professional,
        recipient_user=recipient,
        scope="chart",
        permissions=["view", "download"],
        purpose="Synthetic test",
    )
    text = (
        ConsentTextVersion.objects.filter(purpose="care_sharing", locale="it")
        .order_by("-version")
        .first()
    )
    for decision, expected in [("granted", 200), ("revoked", 404)]:
        PatientConsent.objects.create(
            patient=record, share=share, text_version=text, actor=patient_account, decision=decision
        )
        assert recipient_browser.get(download).status_code == expected
        assert (
            recipient_browser.get(fhir, HTTP_ACCEPT="application/fhir+json").status_code == expected
        )
        if expected == 200:
            assert "subject" not in recipient_browser.get(fhir).json()
            assert recipient_browser.get(fhir_patient).status_code == 404
        assert recipient_browser.get(url).data["count"] == (1 if expected == 200 else 0)
    item = author.post(
        "shares/",
        {
            "patient": str(record.pk),
            "document": created.data["document"],
            "scope": "item",
            "recipient_user": str(recipient.pk),
            "purpose": "Synthetic",
            "permissions": ["view"],
        },
    )
    assert item.status_code == 201, item.content
    grant = Share.objects.get(pk=item.data["id"])
    consent = PatientConsent.objects.create(
        patient=record, share=grant, text_version=text, actor=patient_account, decision="granted"
    )
    assert patient_browser.get(f"fhir/Consent/{consent.pk}").json()["status"] == "active"
    assert recipient_browser.get(fhir).status_code == 200
    assert recipient_browser.get(download).status_code == 404
    assert recipient_browser.get(url).data["results"][0]["can_download"] is False
    assert recipient_browser.get(f"shares/{grant.pk}/patient/").status_code == 404
    assert author.client.delete("/api/v1/" + doc, **csrf).status_code == 204
    assert patient_browser.get(download).status_code == 404
    assert ClinicalDocumentVersion.objects.filter(pk=version.pk).exists()


def test_structured_report_and_observation_are_visible_only_in_care():
    professional = user("report-author@patients.example", "professional")
    approve(professional)
    author = signed(professional)
    record = patient(org_for(professional), professional)
    outsider = signed(user("report-outsider@patients.example"))
    url = f"clinical/patients/{record.pk}/reports/"
    identity = {
        "identifier_kind": "facility",
        "identifier_value": "SYN-REPORT-01",
        "source_birth_date": str(record.birth_date),
    }
    assert author.post(f"clinical/patients/{record.pk}/identifiers/", identity).status_code == 201
    payload = {
        **identity,
        "code": "11502-2",
        "title": "Synthetic panel",
        "effective_at": "2026-01-02T12:00:00Z",
        "observations": [
            {"code": "2345-7", "display": "Synthetic glucose", "value": "90", "unit": "mg/dL"}
        ],
    }
    assert outsider.post(url, payload).status_code == 403
    response = author.post(url, payload)
    assert response.status_code == 201, response.content
    path = f"fhir/DiagnosticReport/{response.data['id']}"
    result = author.get(path, HTTP_ACCEPT="application/fhir+json")
    assert result.status_code == 200
    observation = "fhir/" + result.json()["result"][0]["reference"]
    assert author.get(observation).json()["valueQuantity"]["value"] == 90
    assert outsider.get(path).status_code == 404
    assert outsider.get(observation).json()["resourceType"] == "OperationOutcome"
    assert author.get(f"fhir/Organization/{record.organization_id}").status_code == 200
    assert author.get(f"fhir/Practitioner/{professional.pk}").status_code == 200


def test_real_clamav_storage_restore_and_retention(settings, monkeypatch):
    import os
    from datetime import timedelta

    from django.core.management import call_command
    from django.utils import timezone
    from rest_framework.exceptions import ValidationError

    from identity.clinical import scan, seal
    from identity.clinical_storage import aws, bucket, maintain_version, offload, read_content
    from identity.models import ClinicalDocument

    if os.environ.get("CLINICAL_INTEGRATION_TEST") != "1":
        pytest.skip("Requires a local ClamAV and private S3 bucket.")
    settings.CLINICAL_MASTER_KEY = Fernet.generate_key().decode()
    scan(PDF)
    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    with pytest.raises(ValidationError):
        scan(eicar)

    author = user("storage-author@patients.example", "professional")
    record = patient(org_for(author), author)
    document = ClinicalDocument.objects.create(patient=record, author=author, kind="report")
    version = ClinicalDocumentVersion.objects.create(
        document=document,
        number=1,
        title="Synthetic storage fixture",
        media_type="application/pdf",
        size=len(PDF),
        **seal(PDF, record.organization_id),
    )
    offload(version.pk)
    version.refresh_from_db()
    assert version.object_key
    try:
        assert not version.ciphertext
        assert read_content(version) == PDF
        offload(version.pk)
        old_key = settings.CLINICAL_MASTER_KEY
        settings.CLINICAL_MASTER_KEY = Fernet.generate_key().decode()
        monkeypatch.setenv("CLINICAL_PREVIOUS_MASTER_KEYS", old_key)
        call_command(
            "clinical_storage", "rotate", "--apply", "--tenant", str(record.organization_id)
        )
        monkeypatch.delenv("CLINICAL_PREVIOUS_MASTER_KEYS")
        version.refresh_from_db()
        assert read_content(version) == PDF
        call_command("clinical_storage", "verify", "--tenant", str(record.organization_id))
        document.deleted_at = timezone.now() - timedelta(days=2)
        document.save(update_fields=["deleted_at"])
        target = [
            "--apply",
            "--tenant",
            str(record.organization_id),
            "--document",
            str(document.pk),
        ]
        call_command("clinical_storage", "hold", *target)
        cutoff = timezone.now() - timedelta(days=1)
        maintain_version(version.pk, cutoff=cutoff)
        version.refresh_from_db()
        assert version.purged_at is None
        call_command("clinical_storage", "release-hold", *target)
        call_command(
            "clinical_storage",
            "purge",
            "--apply",
            "--tenant",
            str(record.organization_id),
            "--days",
            "1",
        )
        version.refresh_from_db()
        assert version.purged_at and not version.wrapped_key
        assert (
            not aws("s3")
            .list_objects_v2(Bucket=bucket(), Prefix=version.object_key)
            .get("Contents")
        )
    finally:
        aws("s3").delete_object(Bucket=bucket(), Key=version.object_key)


def test_folder_scope_includes_descendants_and_preserves_patient_boundary():
    professional = user("folder-author@patients.example", "professional")
    approve(professional)
    author = signed(professional)
    patient_account = user("folder-patient@patients.example")
    record = patient(org_for(professional), professional)
    record.account = patient_account
    record.save(update_fields=["account"])
    route = f"clinical/patients/{record.pk}/folders/"
    root = author.post(route, {"title": "Synthetic root"})
    assert root.status_code == 201, root.content
    assert author.get(route).status_code == 200
    assert AuditEvent.objects.filter(
        actor=professional, action="clinical.folders_read", resource_id=record.pk
    ).exists()
    child = author.post(route, {"title": "Synthetic child", "parent_folder": root.data["id"]})
    assert child.status_code == 201, child.content
    other = patient(org_for(professional, "Other synthetic tenant"), professional)
    assert (
        author.post(
            f"clinical/patients/{other.pk}/folders/",
            {
                "title": "Cross tenant",
                "parent_folder": root.data["id"],
            },
        ).status_code
        == 404
    )
    recipient = user("folder-recipient@patients.example", "professional")
    approve(recipient)
    receiver = signed(recipient)
    from identity.models import ClinicalDocument

    document = ClinicalDocument.objects.create(
        patient=record, author=professional, kind="report", folder_id=child.data["id"]
    )
    response = author.post(
        "shares/",
        {
            "patient": str(record.pk),
            "folder": root.data["id"],
            "scope": "folder",
            "recipient_user": str(recipient.pk),
            "purpose": "Synthetic",
            "permissions": ["view", "reshare", "comment"],
        },
    )
    assert response.status_code == 201, response.content
    share = Share.objects.get(pk=response.data["id"])
    messages = f"shares/{share.pk}/messages/"
    for version, status in [(1, 404), (2, 200)]:
        text = ConsentTextVersion.objects.get(purpose="care_sharing", locale="it", version=version)
        PatientConsent.objects.create(
            patient=record,
            share=share,
            text_version=text,
            actor=patient_account,
            decision="granted",
        )
        assert receiver.get(f"clinical/documents/{document.pk}/").status_code == status
        assert receiver.get(messages).status_code == (403 if version == 1 else 200)
    assert receiver.get(f"shares/{share.pk}/patient/").status_code == 404
    assert receiver.get(route).status_code == 404
    assert receiver.post(messages, {"body": "Synthetic clinical discussion"}).status_code == 201
    assert author.get(messages).status_code == 200
    CareRelationship.objects.filter(patient=record, professional=professional).update(active=False)
    assert author.get(messages).status_code == 404
    assert author.post(messages, {"body": "Former grantor"}).status_code == 404
    assert (
        author.post(
            "shares/",
            {
                "parent_share": str(share.pk),
                "patient": str(record.pk),
                "scope": "folder",
                "folder": root.data["id"],
                "permissions": ["view"],
                "purpose": share.purpose,
                "recipient_user": str(patient_account.pk),
            },
        ).status_code
        == 404
    )


def test_import_manifest_is_idempotent_and_rejects_hash_mismatch(settings, monkeypatch, tmp_path):
    import hashlib
    import json
    from types import SimpleNamespace
    from unittest.mock import Mock

    from django.core.management import call_command
    from django.core.management.base import CommandError

    settings.CLINICAL_MASTER_KEY = Fernet.generate_key().decode()
    for name in ("ENDPOINT", "BUCKET", "KEY", "SECRET"):
        monkeypatch.setenv("LEGACY_R2_" + name, "synthetic-fixture")
    professional = user("import-author@patients.example", "professional")
    approve(professional)
    record = patient(org_for(professional), professional)
    record.legacy_source = "d1"
    record.legacy_owner = "synthetic-owner"
    record.legacy_id = "synthetic-patient"
    record.save()
    client = Mock()
    client.meta = SimpleNamespace(endpoint_url="https://synthetic.example")
    client.get_object.side_effect = lambda **kwargs: {"Body": BytesIO(PDF)}
    row = {
        "source": "d1",
        "owner": "synthetic-owner",
        "patient_legacy_id": "synthetic-patient",
        "organization": str(record.organization_id),
        "author": str(professional.pk),
        "key": "synthetic-owner/test",
        "sha256": hashlib.sha256(PDF).hexdigest(),
        "title": "Synthetic",
    }
    manifest = tmp_path / "import.jsonl"
    manifest.write_text(json.dumps(row))
    with (
        patch(
            "identity.management.commands.import_legacy_documents.boto3.client", return_value=client
        ),
        patch("identity.management.commands.import_legacy_documents.scan"),
    ):
        call_command("import_legacy_documents", str(manifest))
        assert ClinicalDocumentVersion.objects.count() == 0
        call_command("import_legacy_documents", str(manifest), "--apply")
        call_command("import_legacy_documents", str(manifest), "--apply")
        assert ClinicalDocumentVersion.objects.count() == 1
        manifest.write_text(json.dumps({**row, "sha256": "0" * 64}))
        with pytest.raises(CommandError):
            call_command("import_legacy_documents", str(manifest), "--apply")


def test_report_identity_scope_preliminary_visibility_and_append_only_history():
    from django.db import DatabaseError, transaction

    from identity.models import ClinicalObservation, ClinicalReport, PatientIdentifier

    professional = user("history-author@patients.example", "professional")
    approve(professional)
    author = signed(professional)
    org = org_for(professional)
    record = patient(org, professional)
    other = patient(org, professional)
    other_org = patient(org_for(professional, "Other tenant"), professional)
    account = user("history-patient@patients.example")
    record.account = account
    record.save(update_fields=["account"])
    owner = signed(account)
    outsider = user("history-outsider@patients.example", "professional")
    approve(outsider)
    outside = signed(outsider)
    assert record.birth_date == other.birth_date == other_org.birth_date
    check = {
        "identifier_kind": "facility",
        "identifier_value": "synthetic-010",
        "source_birth_date": str(record.birth_date),
    }

    def intake(patient, suffix):
        return f"clinical/patients/{patient.pk}/{suffix}/"

    assert owner.post(intake(record, "identifiers"), check).status_code == 403
    assert outside.post(intake(record, "identifiers"), check).status_code == 404
    assert author.post(intake(record, "identifiers"), check).status_code == 201
    assert author.post(intake(other, "identifiers"), check).status_code == 400
    assert author.post(intake(other_org, "identifiers"), check).status_code == 201
    assert PatientIdentifier.objects.count() == 2
    assert PatientIdentifier.objects.get(patient=record).digest != check["identifier_value"]

    episode = {
        **check,
        "started_at": "2026-01-02T10:00:00Z",
        "ended_at": "2026-01-02T12:00:00Z",
    }
    assert (
        author.post(
            intake(record, "encounters"),
            {
                **episode,
                "ended_at": "2026-01-01T12:00:00Z",
            },
        ).status_code
        == 400
    )
    encounter = author.post(intake(record, "encounters"), episode)
    foreign_encounter = author.post(intake(other_org, "encounters"), episode)
    assert encounter.status_code == foreign_encounter.status_code == 201
    encounter_path = f"fhir/Encounter/{encounter.data['id']}"
    assert author.get(encounter_path).json()["status"] == "finished"
    assert owner.get(encounter_path).status_code == 404
    assert outside.get(encounter_path).status_code == 404

    observation = {
        "code": "2345-7",
        "display": "Glucose",
        "value": "90.01",
        "unit": "mg/dL",
        "reference_range": {
            "low": "60",
            "high": "100",
            "min_age_years": 18,
            "laboratory": "Synthetic lab",
        },
    }
    report = {
        **check,
        "code": "11502-2",
        "title": "Source record",
        "encounter_id": str(encounter.data["id"]),
        "effective_at": "2026-01-02T12:00:00Z",
        "observations": [observation],
    }
    url = intake(record, "reports")
    assert author.post(intake(other, "reports"), report).status_code == 400
    assert author.post(url, {**report, "source_birth_date": "1980-01-01"}).status_code == 400
    assert author.post(url, {**report, "identifier_value": "bad-id"}).status_code == 400
    assert (
        author.post(
            url, {**report, "observations": [{**observation, "unit": "mmol/L"}]}
        ).status_code
        == 400
    )
    assert (
        author.post(
            url,
            {
                **report,
                "observations": [
                    {
                        **observation,
                        "reference_range": {
                            "laboratory": "Synthetic lab",
                            "low": "100",
                            "high": "60",
                        },
                    }
                ],
            },
        ).status_code
        == 400
    )
    assert (
        author.post(
            url,
            {
                **report,
                "encounter_id": str(foreign_encounter.data["id"]),
            },
        ).status_code
        == 400
    )
    assert ClinicalReport.objects.count() == 0

    created = author.post(url, report)
    assert created.status_code == 201, created.content
    root = ClinicalReport.objects.get(pk=created.data["id"])
    path = f"fhir/DiagnosticReport/{root.pk}"
    initial = author.get(path).json()
    assert initial["status"] == "preliminary"
    assert initial["encounter"]["reference"] == f"Encounter/{encounter.data['id']}"
    assert owner.get(path).status_code == 404
    assert outside.get(path).status_code == 404
    obs_path = "fhir/" + initial["result"][0]["reference"]
    assert owner.get(obs_path).status_code == 404
    obs = author.get(obs_path).json()
    assert obs["valueQuantity"] == {
        "value": 90.01,
        "unit": "mg/dL",
        "system": "http://unitsofmeasure.org",
        "code": "mg/dL",
    }
    assert obs["referenceRange"][0]["age"]["low"]["code"] == "a"

    correct = f"clinical/reports/{root.pk}/corrections/"
    correction = {
        **report,
        "expected_version": 1,
        "correction_reason": "Source rectified",
        "title": "Revised",
        "observations": [{**observation, "value": "88.01"}],
    }
    assert outside.post(correct, correction).status_code == 404
    assert author.post(correct, correction).data == {"id": root.pk, "version": 2}
    assert author.post(correct, correction).status_code == 409
    assert author.get(path).json()["meta"]["versionId"] == "2"
    provenance_path = f"fhir/Provenance/{root.pk}-v2"
    assert author.get(provenance_path).json()["target"] == [
        {"reference": f"DiagnosticReport/{root.pk}/_history/2"}
    ]
    assert owner.get(provenance_path).status_code == 404
    assert outside.get(provenance_path).status_code == 404
    assert author.get(path + "/_history/1").json() == initial
    from urllib.parse import quote

    assert author.get(path + "?as_of=" + quote(root.recorded_at.isoformat())).json() == initial
    assert author.get(path + "?as_of=2026-01-01T12:00:00").status_code == 400
    assert owner.get(path + "/_history/1").status_code == 404
    assert AuditEvent.objects.filter(action="clinical.report_corrected", organization=org).exists()
    with pytest.raises(DatabaseError), transaction.atomic():
        ClinicalReport.objects.create(
            patient=record,
            author=professional,
            title="Invalid direct link",
            code=report["code"],
            effective_at=root.effective_at,
            encounter_id=foreign_encounter.data["id"],
        )
    with pytest.raises(DatabaseError), transaction.atomic():
        ClinicalReport.objects.create(
            patient=other,
            author=professional,
            title="Invalid revision link",
            code=report["code"],
            effective_at=root.effective_at,
            recorded_at=root.recorded_at,
            version=3,
            root=root,
            previous=root.revisions.get(version=2),
            correction_reason="wrong patient",
        )
    for model, field, value in (
        (ClinicalReport, "title", "Overwritten"),
        (ClinicalObservation, "label", "Overwritten"),
        (PatientIdentifier, "digest", "Overwritten"),
    ):
        with pytest.raises(DatabaseError), transaction.atomic():
            model.objects.all().update(**{field: value})


def test_report_upload_requires_confirmation_before_scanning(settings):
    settings.CLINICAL_MASTER_KEY = Fernet.generate_key().decode()
    professional = user("intake-author@patients.example", "professional")
    approve(professional)
    author = signed(professional)
    record = patient(org_for(professional), professional)
    base = f"/api/v1/clinical/patients/{record.pk}"
    check = {
        "identifier_kind": "facility",
        "identifier_value": "SYN-UPLOAD",
        "source_birth_date": str(record.birth_date),
    }
    assert author.post(f"clinical/patients/{record.pk}/identifiers/", check).status_code == 201
    csrf = author.client.cookies["csrftoken"].value

    def upload(url, fields):
        return author.client.post(
            url,
            {
                "title": "Synthetic report",
                "file": SimpleUploadedFile("report.pdf", PDF, content_type="application/pdf"),
                **fields,
            },
            format="multipart",
            HTTP_X_CSRFTOKEN=csrf,
        )

    with patch("identity.clinical.scan") as scan:
        assert upload(base + "/documents/", {"kind": "report"}).status_code == 400
        scan.assert_not_called()
        first = upload(base + "/documents/", {"kind": "report", **check})
        assert first.status_code == 201, first.content
        versions = f"/api/v1/clinical/documents/{first.data['document']}/"
        assert upload(versions, {"kind": "other"}).status_code == 400
        assert upload(versions, check).status_code == 201
        assert scan.call_count == 2


def test_legacy_report_has_no_invented_timestamp_signature_or_ucum():
    from django.utils import timezone

    from identity.models import ClinicalObservation, ClinicalReport

    professional = user("legacy-report-author@patients.example", "professional")
    approve(professional)
    record = patient(org_for(professional), professional)
    account = user("legacy-report-patient@patients.example")
    record.account = account
    record.save(update_fields=["account"])
    legacy = ClinicalReport.objects.create(
        patient=record,
        author=professional,
        title="Legacy",
        code="24323-8",
        effective_at=timezone.now(),
    )
    observation = ClinicalObservation.objects.create(
        report=legacy,
        code="2345-7",
        label="Legacy observation",
        value=90,
        unit="legacy unit",
    )
    browser = signed(account)
    path = f"fhir/DiagnosticReport/{legacy.pk}"
    report = browser.get(path).json()
    assert report["status"] == "unknown"
    assert report["meta"] == {"versionId": "1"}
    assert browser.get(path + "?as_of=2026-11-01T10:00:00Z").status_code == 404
    assert browser.get(f"fhir/Provenance/{legacy.pk}-v1").status_code == 404
    result = browser.get(f"fhir/Observation/{observation.pk}").json()
    assert result["valueQuantity"] == {"value": 90, "unit": "legacy unit"}
