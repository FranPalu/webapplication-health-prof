"""Create a disposable synthetic professional and patient for the browser smoke test."""

import json
import secrets
import uuid
from datetime import date

from django.conf import settings
from django.db import transaction

from identity.models import (
    CareRelationship,
    Membership,
    Organization,
    Patient,
    ProfessionalVerification,
    User,
)

if not settings.DEBUG:
    raise RuntimeError("Synthetic fixture requires DEBUG")

email = f"m3-browser-{uuid.uuid4()}@patients.example"
password = secrets.token_urlsafe(32)
with transaction.atomic():
    professional = User.objects.create_user(
        email, password, role="professional", email_verified=True
    )
    ProfessionalVerification.objects.create(
        user=professional, register="Synthetic", license_number="SYNTHETIC", status="approved"
    )
    organization = Organization.objects.create(name="Studio sintetico M3 E2E", kind="clinic")
    Membership.objects.create(organization=organization, user=professional, role="professional")
    patient_password = secrets.token_urlsafe(32)
    account = User.objects.create_user(
        f"m4-browser-{uuid.uuid4()}@patients.example",
        patient_password,
        role="patient",
        email_verified=True,
    )
    record = Patient.objects.create(
        account=account,
        organization=organization,
        first_name="E2E",
        last_name="Sintetico",
        birth_date=date(1990, 1, 1),
    )
    CareRelationship.objects.create(patient=record, professional=professional)
print(
    json.dumps(
        {
            "email": email,
            "password": password,
            "patient_email": account.email,
            "patient_password": patient_password,
            "patient": str(record.pk),
        }
    )
)
