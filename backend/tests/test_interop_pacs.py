"""Synthetic single-frame DICOM, tag minimization and authorized DICOMweb."""

import json
import os
from io import BytesIO
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.db import DatabaseError, transaction
from pydicom import dcmread, dcmwrite
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian
from test_identity import approve, signed, user
from test_interop_fhir import scenario as fhir_scenario  # noqa: F401

from identity.clinical import seal
from identity.interop_pacs import deidentify, pacs_request
from identity.models import (
    CareRelationship,
    ClinicalDocument,
    ClinicalDocumentVersion,
    PacsStudyLink,
)

pytestmark = pytest.mark.django_db


def image():
    data = Dataset()
    data.SOPClassUID = "1.2.840.10008.5.1.4.1.1.7"
    data.SOPInstanceUID = "2.25.1234567891"
    data.StudyInstanceUID = "2.25.1234567892"
    data.SeriesInstanceUID = "2.25.1234567893"
    data.PatientName = "SYNTHETIC^NOT-A-PATIENT"
    data.PatientID = "SYNTHETIC-P5"
    data.IssuerOfPatientID = "SYNTHETIC-AUTHORITY"
    data.PatientBirthDate = "19900101"
    data.Modality = "OT"
    data.BurnedInAnnotation = "NO"
    data.Rows = data.Columns = 32
    data.SamplesPerPixel = 1
    data.PhotometricInterpretation = "MONOCHROME2"
    data.BitsAllocated = data.BitsStored = 8
    data.HighBit = 7
    data.PixelRepresentation = 0
    data.PixelData = bytes(range(256)) * 4
    data.add_new((0x0011, 0x0010), "LO", "SYNTHETIC-PRIVATE-CREATOR")
    data.add_new((0x0011, 0x1001), "LO", "SYNTHETIC-PRIVATE-NOTE")
    data.file_meta = FileMetaDataset()
    data.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    data.file_meta.MediaStorageSOPClassUID = data.SOPClassUID
    data.file_meta.MediaStorageSOPInstanceUID = data.SOPInstanceUID
    output = BytesIO()
    dcmwrite(output, data, enforce_file_format=True)
    return output.getvalue()


@pytest.fixture
def scenario(fhir_scenario, settings):  # noqa: F811
    settings.CLINICAL_MASTER_KEY = Fernet.generate_key().decode()
    settings.PACS_ASSIGNING_AUTHORITY = "SYNTHETIC-AUTHORITY"
    author, account, record = fhir_scenario
    document = ClinicalDocument.objects.create(patient=record, author=author, kind="report")
    content = image()
    version = ClinicalDocumentVersion.objects.create(
        document=document,
        number=1,
        title="Synthetic image",
        media_type="application/dicom",
        size=len(content),
        **seal(content, record.organization_id),
    )
    return author, account, record, version


def test_dicom_minimization_remaps_uids_and_preserves_pixels():
    original = image()
    safe, study, series, instance = deidentify(original, b"SYNTHETIC-NAMESPACE-KEY-NOT-A-SECRET")
    dataset = dcmread(BytesIO(safe))
    source = dcmread(BytesIO(original))
    assert dataset.PixelData == source.PixelData
    assert str(dataset.PatientName) == "" and str(dataset.PatientBirthDate) == ""
    assert dataset.PatientID != source.PatientID and dataset.PatientIdentityRemoved == "YES"
    assert not any(element.tag.is_private for element in dataset.iterall())
    assert study != str(source.StudyInstanceUID) and dataset.SOPInstanceUID == instance
    assert deidentify(original, b"SYNTHETIC-NAMESPACE-KEY-NOT-A-SECRET")[1:] == (
        study,
        series,
        instance,
    )
    assert deidentify(original, b"SYNTHETIC-OTHER-TENANT-AND-PATIENT-KEY")[1] != study
    assert b"PRIVATE-NOTE" not in safe and b"NOT-A-PATIENT" not in safe


@pytest.mark.parametrize(
    "name,value",
    [
        ("BurnedInAnnotation", "YES"),
        ("NumberOfFrames", 2),
        ("Rows", 0),
        ("Modality", "CT"),
        ("PixelData", b"x"),
        ("HighBit", 4),
    ],
)
def test_dicom_uncertain_or_unsupported_images_are_rejected(name, value):
    dataset = dcmread(BytesIO(image()))
    setattr(dataset, name, value)
    output = BytesIO()
    dcmwrite(output, dataset, enforce_file_format=True)
    with pytest.raises(ValueError):
        deidentify(output.getvalue(), b"SYNTHETIC-NAMESPACE-KEY-NOT-A-SECRET")


def test_pacs_store_and_dicomweb_deny_other_roles_and_revoked_care(scenario):
    author, account, record, version = scenario
    browser = signed(author)
    path = f"interop/patients/{record.pk}/pacs/"
    fields = {
        "version": str(version.pk),
        "identifier_kind": "facility",
        "identifier_value": "SYNTHETIC-P5",
        "source_birth_date": str(record.birth_date),
    }
    stored = {}

    def stow(method, path, **kwargs):
        assert method == "POST" and path == "/studies"
        raw = kwargs["body"].split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n--", 1)[0]
        dataset = dcmread(BytesIO(raw))
        stored["instance"] = str(dataset.SOPInstanceUID)
        return json.dumps(
            {
                "00081199": {
                    "vr": "SQ",
                    "Value": [{"00081155": {"vr": "UI", "Value": [stored["instance"]]}}],
                }
            }
        ).encode(), "application/dicom+json"

    with patch("identity.interop_pacs.pacs_request", side_effect=stow) as transport:
        response = browser.post(path, fields)
        assert response.status_code == 201, response.content
        study = response.data["study_uid"]
        assert browser.post(path, fields).status_code == 201 and transport.call_count == 1
    link = PacsStudyLink.objects.get()
    with pytest.raises(DatabaseError), transaction.atomic():
        PacsStudyLink.objects.filter(pk=link.pk).update(study_uid="2.25.1")
    query = f"dicom-web/studies?StudyInstanceUID={study}"
    with patch(
        "identity.interop_pacs.pacs_request",
        return_value=(
            json.dumps(
                [
                    {
                        "0020000D": {"vr": "UI", "Value": [study]},
                        "00100010": {"vr": "PN", "Value": [{"Alphabetic": "PRIVATE"}]},
                        "00081190": {"vr": "UR", "Value": ["http://internal-secret"]},
                    }
                ]
            ).encode(),
            "application/dicom+json",
        ),
    ):
        result = browser.get(query)
        assert result.status_code == 200, result.content
        assert b"PRIVATE" not in result.content and b"internal-secret" not in result.content
    assert signed(account).get(query).status_code == 403
    other = user("p5-pacs-outsider@patients.example", "professional")
    approve(other)
    assert signed(other).get(query).status_code == 404
    with patch("identity.interop_pacs.pacs_request") as transport:
        assert browser.get(f"dicom-web/studies/{study}/../config").status_code in (404, 400)
        CareRelationship.objects.filter(patient=record, professional=author).update(active=False)
        assert browser.get(query).status_code == 404
        transport.assert_not_called()


def test_actual_orthanc_stow_qido_wado_if_enabled(settings):
    if os.environ.get("PACS_INTEGRATION_TEST") != "1":
        pytest.skip("Explicit synthetic Orthanc profile integration required")
    # The regular suite has deterministic protocol tests; CI also executes this real profile.
    settings.PACS_DICOMWEB_URL = os.environ["PACS_DICOMWEB_URL"]
    settings.PACS_USERNAME = os.environ["PACS_USERNAME"]
    settings.PACS_PASSWORD = os.environ["PACS_PASSWORD"]
    data, study, series, instance = deidentify(image(), b"SYNTHETIC-ACTUAL-PACS-TEST-NAMESPACE")
    boundary = "p5-real-synthetic"
    body = (
        f"--{boundary}\r\nContent-Type: application/dicom\r\n\r\n".encode()
        + data
        + f"\r\n--{boundary}--\r\n".encode()
    )
    result, _ = pacs_request(
        "POST",
        "/studies",
        body=body,
        content_type=f'multipart/related; type="application/dicom"; boundary={boundary}',
    )
    assert instance in result.decode()
    result, _ = pacs_request("GET", "/studies?StudyInstanceUID=" + study)
    assert study in result.decode()
    pixel, media = pacs_request(
        "GET",
        f"/studies/{study}/series/{series}/instances/{instance}/frames/1",
        accept='multipart/related; type="application/octet-stream"',
    )
    assert "multipart/related" in media and dcmread(BytesIO(data)).PixelData in pixel


def test_embedded_dicom_patient_must_match_the_registered_source(scenario):
    author, _, record, version = scenario
    source = dcmread(BytesIO(image()))
    source.PatientID = "SYNTHETIC-WRONG-PATIENT"
    output = BytesIO()
    dcmwrite(output, source, enforce_file_format=True)
    altered = output.getvalue()
    wrong = ClinicalDocumentVersion.objects.create(
        document=version.document,
        number=2,
        title="Synthetic wrong patient source",
        media_type="application/dicom",
        size=len(altered),
        **seal(altered, record.organization_id),
    )
    with patch("identity.interop_pacs.pacs_request") as transport:
        result = signed(author).post(
            f"interop/patients/{record.pk}/pacs/",
            {
                "version": str(wrong.pk),
                "identifier_kind": "facility",
                "identifier_value": "SYNTHETIC-P5",
                "source_birth_date": str(record.birth_date),
            },
        )
        assert result.status_code == 400, result.content
        transport.assert_not_called()


def test_nested_identifiers_cannot_hide_inside_allowed_public_tags():
    source = dcmread(BytesIO(image()))
    nested = Dataset()
    nested.PatientName = "SYNTHETIC-NESTED-IDENTIFIER"
    source.add_new((0x0028, 0x0030), "SQ", [nested])
    output = BytesIO()
    dcmwrite(output, source, enforce_file_format=True)
    with pytest.raises(ValueError, match="representation"):
        deidentify(output.getvalue(), b"SYNTHETIC-NAMESPACE-KEY-NOT-A-SECRET")
