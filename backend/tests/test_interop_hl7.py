"""Synthetic ADT/ORM/ORU profiles and durable commit acknowledgments."""

import hashlib

import pytest
from cryptography.fernet import Fernet
from django.db import DatabaseError, transaction
from test_identity import signed
from test_interop_fhir import scenario as fhir_scenario  # noqa: F401

from identity.analysis import decode_tenant
from identity.interop_hl7 import InvalidHL7, parse_message
from identity.models import ClinicalReport, InteropReceipt, LabOrder

pytestmark = pytest.mark.django_db


@pytest.fixture
def scenario(fhir_scenario, settings):  # noqa: F811
    settings.HL7_SENDING_APPLICATION = "SYNTHETIC-LIS"
    settings.HL7_ASSIGNING_AUTHORITY = "SYNTHETIC-AUTHORITY"
    settings.CLINICAL_MASTER_KEY = Fernet.generate_key().decode()
    return fhir_scenario


def message(record, kind="ORU^R01", control="synthetic-01"):
    fields = [
        "MSH",
        "^~\\&",
        "SYNTHETIC-LIS",
        "SYNTHETIC",
        "CLARIA",
        "",
        "20261109100000+0100",
        "",
        kind,
        control,
        "T",
        "2.5.1",
        "",
        "",
        "AL",
        "AL",
    ]
    lines = [
        "|".join(fields),
        f"PID|1||SYNTHETIC-P5^^^SYNTHETIC-AUTHORITY^MR||SYNTHETIC||{str(record.birth_date).replace('-', '')}",
    ]
    if kind == "ADT^A01":
        lines.append("PV1|1|O")
    else:
        if kind == "ORM^O01":
            lines.append("ORC|NW")
        obr = ["OBR", "1", "", "", "11502-2^Synthetic lab^LN"] + [""] * 20 + ["F"]
        lines.append("|".join(obr))
        if kind == "ORU^R01":
            lines.append("OBX|1|NM|2345-7^Synthetic glucose^LN||85|mg/dL^^UCUM|||||F")
    return "\r".join(lines) + "\r"


@pytest.mark.parametrize("kind", ["ADT^A01", "ORM^O01", "ORU^R01"])
def test_messages_are_identified_encrypted_and_quarantined_not_applied(scenario, kind):
    author, _, record = scenario
    browser = signed(author)
    raw = message(record, kind)
    path = f"interop/patients/{record.pk}/hl7/"
    response = browser.post(path, {"message": raw})
    assert response.status_code == 202, response.content
    assert response.data["state"] == "quarantined" and "MSA|CA|" in response.data["ack"]
    assert response.data["application_review"] == "not_performed"
    assert browser.post(path, {"message": raw}).data["id"] == response.data["id"]
    assert not ClinicalReport.objects.exists() and not LabOrder.objects.exists()
    receipt = InteropReceipt.objects.get()
    detail = browser.get(f"interop/hl7-receipts/{receipt.pk}/")
    assert detail.status_code == 200 and detail.data["raw_message"] == raw
    assert b"SYNTHETIC-P5" not in bytes(receipt.ciphertext)
    saved = decode_tenant(receipt, record.organization_id)
    assert saved["input_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert saved["parsed"]["status"] == "quarantined"
    with pytest.raises(DatabaseError), transaction.atomic():
        InteropReceipt.objects.filter(pk=receipt.pk).delete()
    if kind == "ORU^R01":
        assert browser.post(path, {"message": raw.replace("|85|", "|86|")}).status_code == 409


@pytest.mark.parametrize(
    "old,new",
    [
        ("|T|2.5.1", "|P|2.5.1"),
        ("SYNTHETIC-LIS", "OTHER"),
        ("SYNTHETIC-AUTHORITY", "OTHER"),
        ("|NM|", "|ST|"),
        ("|85|", "|<85|"),
        ("mg/dL^^UCUM", "mmol/L^^UCUM"),
        ("|AL|AL", "||"),
        ("ORU^R01", "ORU^R99"),
        ("2.5.1", "2.8"),
        ("|||||F", "|60-100||||F"),
    ],
)
def test_unsupported_hl7_profiles_fail_closed(scenario, old, new):
    _, _, record = scenario
    with pytest.raises(InvalidHL7):
        parse_message(message(record).replace(old, new), "SYNTHETIC-LIS", "SYNTHETIC-AUTHORITY")


def test_hl7_rejects_wrong_patient_and_unknown_segments(scenario):
    author, _, record = scenario
    browser = signed(author)
    raw = message(record)
    path = f"interop/patients/{record.pk}/hl7/"
    assert browser.post(path, {"message": raw.replace("SYNTHETIC-P5", "WRONG")}).status_code == 400
    assert (
        browser.post(path, {"message": raw + "NTE|1||Do not discard this note\r"}).status_code
        == 400
    )
    assert not InteropReceipt.objects.exists()
