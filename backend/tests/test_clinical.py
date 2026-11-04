from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.core.files.uploadedfile import SimpleUploadedFile
from test_identity import approve, org_for, patient, signed, user

from identity.models import ClinicalDocumentVersion, ConsentTextVersion, PatientConsent, Share

pytestmark = pytest.mark.django_db
PDF = b"%PDF-1.7\nsynthetic content"


def test_clinical_version_lifecycle_and_access(settings):
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
    assert {resource["type"] for resource in types} == {"Patient", "DocumentReference"}
    assert outsider.get(download).status_code == 404
    assert outsider.get(fhir).status_code == 404
    assert outsider.get(url + "?q=Synthetic").data["count"] == 0
    assert patient_browser.get(url + "?q=Synthetic").data["count"] == 1
    assert author.get(url + "?q=Synthetic").data["count"] == 2
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
    text = ConsentTextVersion.objects.filter(purpose="care_sharing", locale="it").first()
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
    assert author.client.delete("/api/v1/" + doc, **csrf).status_code == 204
    assert patient_browser.get(download).status_code == 404
    assert ClinicalDocumentVersion.objects.filter(pk=version.pk).exists()
