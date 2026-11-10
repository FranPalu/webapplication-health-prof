"""Test-only synthetic PACS fixture; called in a disposable DEBUG database."""

import json
import secrets
import uuid
from datetime import date

import pyotp
from django.conf import settings
from rest_framework.test import APIClient
from test_interop_pacs import image

from identity.clinical import seal
from identity.models import (
    CareRelationship,
    ClinicalDocument,
    ClinicalDocumentVersion,
    Membership,
    Organization,
    Patient,
    PatientIdentifier,
    ProfessionalVerification,
    User,
)
from identity.patient_identification import identifier_digest
from identity.security import cipher

if not settings.DEBUG or not settings.FHIR_INTEROP_ENABLED:
    raise RuntimeError("Only synthetic interoperability testing is allowed")
secret = pyotp.random_base32()
password = secrets.token_urlsafe(32)
actor = User.objects.create_user(
    f"p5-viewer-{uuid.uuid4()}@patients.example",
    password,
    role="professional",
    email_verified=True,
    mfa_enabled=True,
    mfa_secret=cipher().encrypt(secret.encode()).decode(),
)
ProfessionalVerification.objects.create(
    user=actor, register="SYNTHETIC", license_number="SYNTHETIC", status="approved"
)
org = Organization.objects.create(name="P5 SYNTHETIC ONLY", kind="clinic")
Membership.objects.create(user=actor, organization=org, role="admin")
record = Patient.objects.create(
    organization=org, first_name="SYNTHETIC", last_name="NOT A PATIENT", birth_date=date(1990, 1, 1)
)
CareRelationship.objects.create(patient=record, professional=actor)
PatientIdentifier.objects.create(
    patient=record,
    organization=org,
    kind="facility",
    digest=identifier_digest(org.pk, "facility", "SYNTHETIC-P5"),
    recorded_by=actor,
)
document = ClinicalDocument.objects.create(patient=record, author=actor, kind="report")
raw = image()
version = ClinicalDocumentVersion.objects.create(
    document=document,
    number=1,
    title="SYNTHETIC viewer fixture",
    media_type="application/dicom",
    size=len(raw),
    **seal(raw, org.pk),
)
# Fixture setup bypasses CSRF only here; the browser test logs in and verifies MFA normally.
client = APIClient()
client.force_login(actor)
session = client.session
session["auth_version"] = actor.auth_version
session["mfa_version"] = actor.auth_version
session.save()
result = client.post(
    f"/api/v1/interop/patients/{record.pk}/pacs/",
    {
        "version": str(version.pk),
        "identifier_kind": "facility",
        "identifier_value": "SYNTHETIC-P5",
        "source_birth_date": "1990-01-01",
    },
    format="json",
)
if result.status_code != 201:
    raise RuntimeError("Synthetic PACS fixture preparation failed")
print(
    json.dumps(
        {
            "email": actor.email,
            "password": password,
            "totp_secret": secret,
            "study_uid": result.data["study_uid"],
        }
    )
)
