"""Create a disposable synthetic professional and patient for the browser smoke test."""

import json
import secrets
import uuid
from datetime import date

import pyotp
from django.conf import settings
from django.db import transaction

from identity.analysis_registry import manifest
from identity.models import (
    AnalysisPolicyEvent,
    CareRelationship,
    Membership,
    Organization,
    Patient,
    ProfessionalVerification,
    User,
)
from identity.security import cipher

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
    AnalysisPolicyEvent.objects.create(
        organization=organization,
        author=professional,
        enabled=True,
        manifest_hash=manifest()[1],
        reason="Synthetic browser fixture, not clinical approval",
    )
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
    workspaces = {}
    for key, role, kind, staff in (
        ("organization", "organization_admin", "clinic", False),
        ("pharmacy", "organization_admin", "pharmacy", False),
        ("research", "researcher", "research", False),
        ("platform", "organization_admin", "clinic", True),
    ):
        secret = pyotp.random_base32()
        workspace_password = secrets.token_urlsafe(32)
        member = User.objects.create_user(
            f"m8-{key}-{uuid.uuid4()}@patients.example",
            workspace_password,
            role=role,
            email_verified=True,
            is_staff=staff,
            mfa_enabled=True,
            mfa_secret=cipher().encrypt(secret.encode()).decode(),
        )
        tenant = Organization.objects.create(name=f"Organizzazione sintetica {key}", kind=kind)
        Membership.objects.create(organization=tenant, user=member, role="admin")
        workspaces[key] = {
            "email": member.email,
            "password": workspace_password,
            "totp_secret": secret,
            "organization": str(tenant.pk),
        }
print(
    json.dumps(
        {
            "email": email,
            "password": password,
            "patient_email": account.email,
            "patient_password": patient_password,
            "patient": str(record.pk),
            "workspaces": workspaces,
        }
    )
)
