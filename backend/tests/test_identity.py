import io
import json
import re
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pyotp
import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from identity.models import (
    AccountToken,
    AuditEvent,
    CareRelationship,
    Membership,
    Organization,
    Patient,
    ProfessionalVerification,
    RecoveryCode,
    User,
)
from identity.security import cipher, consume_recovery, digest
from identity.services import issue_token

pytestmark = pytest.mark.django_db
PASSWORD = "Synthetic-Only!long-passphrase-847"


class Browser:
    def __init__(self):
        self.client = APIClient(enforce_csrf_checks=True)
        assert self.get("auth/session/").status_code == 200

    def get(self, path, **extra):
        return self.client.get("/api/v1/" + path, **extra)

    def post(self, path, body):
        return self.client.post(
            "/api/v1/" + path,
            body,
            format="json",
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
        )


def user(email="patient@patients.example", role="patient", verified=True, staff=False):
    return User.objects.create_user(
        email, PASSWORD, role=role, email_verified=verified, is_staff=staff
    )


def signed(account, mfa=True):
    browser = Browser()
    assert (
        browser.post("auth/login/", {"email": account.email, "password": PASSWORD}).status_code
        == 200
    )
    if mfa and account.requires_mfa:
        enroll(browser)
    return browser


def enroll(browser):
    response = browser.post("auth/mfa/setup/", {"password": PASSWORD})
    assert response.status_code == 200, response.data
    secret = parse_qs(urlparse(response.data["uri"]).query)["secret"][0]
    code = pyotp.TOTP(secret).now()
    result = browser.post("auth/mfa/confirm/", {"code": code})
    assert result.status_code == 200, result.data
    return secret, code, result.data["recovery_codes"]


def emailed_token():
    return re.search(r"#token=([^\s]+)", mail.outbox[-1].body).group(1)


def org_for(account, name="Synthetic clinic"):
    org = Organization.objects.create(name=name, kind="clinic")
    Membership.objects.create(user=account, organization=org, role="admin")
    return org


def approve(account):
    return ProfessionalVerification.objects.create(
        user=account,
        register="Synthetic register",
        license_number="SYNTHETIC-ONLY",
        status="approved",
    )


def patient(org, professional=None):
    p = Patient.objects.create(
        organization=org, first_name="Fittizio", last_name="Sintetico", birth_date="1990-01-01"
    )
    if professional:
        CareRelationship.objects.create(patient=p, professional=professional)
    return p


def test_register_verify_login_csrf_and_headers():
    b = Browser()
    assert b.client.post("/api/v1/auth/register/", {}).status_code == 403
    assert (
        b.post(
            "auth/register/", {"email": "a@patients.example", "password": "weak", "role": "patient"}
        ).status_code
        == 400
    )
    assert (
        b.post(
            "auth/register/", {"email": "a@patients.example", "password": PASSWORD, "role": "admin"}
        ).status_code
        == 400
    )
    body = {
        "email": "A@patients.example",
        "password": PASSWORD,
        "role": "patient",
        "is_staff": True,
    }
    assert b.post("auth/register/", body).status_code == 202
    account = User.objects.get(email="a@patients.example")
    assert account.password.startswith("argon2$") and not account.is_staff
    assert b.post("auth/login/", {"email": account.email, "password": PASSWORD}).status_code == 403
    token = emailed_token()
    assert not AccountToken.objects.filter(digest=token).exists()
    assert b.post("auth/verify/", {"token": token}).status_code == 200
    assert b.post("auth/verify/", {"token": token}).status_code == 400
    assert b.post("auth/login/", {"email": account.email, "password": PASSWORD}).status_code == 200
    assert b.get("auth/session/").data["email_verified"]
    assert b.post("auth/logout/", {}).status_code == 200
    assert (
        b.get(
            "patients/",
            HTTP_OAI_AUTHENTICATED_USER_ID=str(account.id),
            HTTP_OAI_AUTHENTICATED_USER_EMAIL=account.email,
        ).status_code
        == 403
    )
    assert b.get("auth/session/")["Cache-Control"] == "no-store"
    assert "password" not in str(b.get("auth/session/").data)


def test_registration_duplicate_resend_expiry_and_password_recovery():
    account = user(verified=False)
    b = Browser()
    body = {"email": account.email, "password": PASSWORD, "role": "patient"}
    assert b.post("auth/register/", body).status_code == 202
    assert b.post("auth/resend/", {"email": account.email}).status_code == 202
    first = emailed_token()
    assert b.post("auth/resend/", {"email": account.email}).status_code == 202
    assert b.post("auth/verify/", {"token": first}).status_code == 400
    last = emailed_token()
    AccountToken.objects.filter(digest=digest(last)).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert b.post("auth/verify/", {"token": last}).status_code == 400
    account.email_verified = True
    account.save()
    b = signed(account)
    assert b.post("auth/reset/request/", {"email": "absent@patients.example"}).status_code == 202
    assert b.post("auth/reset/request/", {"email": account.email}).status_code == 202
    token = emailed_token()
    public = Browser()
    assert (
        public.post(
            "auth/reset/", {"token": token, "password": "Another-strong!synthetic-8372"}
        ).status_code
        == 200
    )
    assert public.post("auth/reset/", {"token": token, "password": PASSWORD}).status_code == 400
    assert b.get("auth/session/").data["status"] == "anonymous"


def test_mfa_enrollment_replay_recovery_and_reset():
    account = user(role="professional")
    b = signed(account, mfa=False)
    assert b.get("organizations/").status_code == 403
    assert b.post("auth/mfa/verify/", {"code": "000000"}).status_code == 403
    assert b.post("auth/mfa/setup/", {"password": "wrong"}).status_code == 403
    secret, code, codes = enroll(b)
    account.refresh_from_db()
    assert secret not in account.mfa_secret
    assert cipher().decrypt(account.mfa_secret.encode()).decode() == secret
    assert RecoveryCode.objects.filter(user=account).count() == 8
    assert not RecoveryCode.objects.filter(digest=codes[0]).exists()
    assert b.post("auth/mfa/setup/", {"password": PASSWORD}).status_code == 403
    assert b.post("auth/mfa/confirm/", {"code": code}).status_code == 403
    b.post("auth/logout/", {})
    assert b.post("auth/login/", {"email": account.email, "password": PASSWORD}).status_code == 200
    assert b.post("auth/mfa/verify/", {"code": code}).status_code == 403
    assert b.post("auth/mfa/verify/", {"code": codes[0]}).status_code == 200
    assert b.post("auth/mfa/verify/", {"code": codes[0]}).status_code == 403
    assert b.post("auth/mfa/reset/", {"password": "wrong"}).status_code == 403
    assert b.post("auth/mfa/reset/", {"password": PASSWORD}).status_code == 200
    account.refresh_from_db()
    assert not account.mfa_enabled and not account.mfa_secret
    assert not RecoveryCode.objects.filter(user=account).exists()
    assert b.get("organizations/").status_code == 403


def test_totp_next_step_and_failed_rate_limits_persist():
    account = user(role="organization_admin")
    b = signed(account, mfa=False)
    secret, _, _ = enroll(b)
    b.post("auth/logout/", {})
    b.post("auth/login/", {"email": account.email, "password": PASSWORD})
    future = timezone.now().timestamp() + 30
    with patch("identity.security.time.time", return_value=future):
        assert (
            b.post("auth/mfa/verify/", {"code": pyotp.TOTP(secret).at(future)}).status_code == 200
        )
    for _ in range(16):
        result = b.post("auth/mfa/verify/", {"code": "invalid"})
    assert result.status_code == 429
    other = Browser()
    for _ in range(31):
        result = other.post("auth/login/", {"email": account.email, "password": "wrong"})
    assert result.status_code == 429


def test_professional_review_permissions_and_approval():
    professional = user(role="professional")
    b = signed(professional)
    assert b.post("organizations/", {"name": "Test", "kind": "clinic"}).status_code == 403
    assert (
        b.post(
            "professional/verification/", {"register": "Test", "license_number": "SYNTHETIC"}
        ).status_code
        == 202
    )
    assert b.get("admin/verifications/").status_code == 403
    admin = user("admin@patients.example", "organization_admin", staff=True)
    a = signed(admin)
    assert a.get("admin/verifications/").data["count"] == 1
    assert (
        a.post(
            f"admin/verifications/{professional.id}/",
            {"status": "approved", "reason": "Manual synthetic check"},
        ).status_code
        == 200
    )
    result = b.post("organizations/", {"name": "Test", "kind": "practice"})
    assert result.status_code == 201
    assert b.get("organizations/").data["count"] == 1
    ProfessionalVerification.objects.create(user=admin, register="x", license_number="x")
    assert (
        a.post(
            f"admin/verifications/{admin.id}/", {"status": "approved", "reason": "self"}
        ).status_code
        == 403
    )
    assert (
        b.post(
            "professional/verification/", {"register": "Changed", "license_number": "Changed"}
        ).status_code
        == 202
    )
    assert b.get("auth/session/").data["verification_status"] == "pending"
    assert b.post("organizations/", {"name": "Denied", "kind": "clinic"}).status_code == 403
    patient_browser = signed(user("other@patients.example"))
    assert (
        patient_browser.post(
            "professional/verification/", {"register": "x", "license_number": "x"}
        ).status_code
        == 403
    )
    assert (
        patient_browser.post("organizations/", {"name": "Denied", "kind": "clinic"}).status_code
        == 403
    )


def test_cross_tenant_patient_lists_details_and_no_admin_clinical_access():
    professional = user(role="professional")
    approve(professional)
    b = signed(professional)
    own = org_for(professional)
    other = Organization.objects.create(name="Other", kind="hospital")
    p = patient(own, professional)
    hidden = patient(own)
    foreign = patient(other)
    path = f"organizations/{own.id}/patients/"
    assert b.get(path).data["count"] == 1
    assert b.get(path + f"{p.id}/").status_code == 200
    assert b.get(path + f"{hidden.id}/").status_code == 404
    assert b.get(path + f"{foreign.id}/").status_code == 404
    assert b.get(f"organizations/{other.id}/patients/").data["count"] == 0
    assert (
        b.post(
            f"organizations/{other.id}/patients/",
            {"first_name": "A", "last_name": "B", "birth_date": "1990-01-01"},
        ).status_code
        == 403
    )
    assert (
        b.post(path, {"first_name": "A", "last_name": "B", "birth_date": "2990-01-01"}).status_code
        == 400
    )
    assert (
        b.post(
            path,
            {
                "first_name": "A",
                "last_name": "B",
                "birth_date": "1990-01-01",
                "organization": str(other.id),
            },
        ).status_code
        == 201
    )
    assert b.get(path).data["count"] == 2
    CareRelationship.objects.filter(patient=p).update(active=False)
    assert b.get(path + f"{p.id}/").status_code == 404
    admin = user("admin@patients.example", "organization_admin", staff=True)
    a = signed(admin)
    Membership.objects.create(user=admin, organization=own, role="admin")
    assert a.get(path).data["count"] == 0
    assert a.get(path + f"{hidden.id}/").status_code == 404
    assert not any(
        x in str(list(AuditEvent.objects.values("action", "resource_id")))
        for x in ["Fittizio", "Sintetico"]
    )


def test_membership_and_relationship_changes_invalidate_sessions():
    owner = user(role="organization_admin")
    b = signed(owner)
    org = org_for(owner)
    professional = user("professional@patients.example", "professional")
    approve(professional)
    pclient = signed(professional)
    path = f"organizations/{org.id}/memberships/"
    assert pclient.post(path, {"email": owner.email, "role": "admin"}).status_code == 403
    assert b.post(path, {"email": owner.email, "role": "admin"}).status_code == 400
    assert b.post(path, {"email": professional.email, "role": "professional"}).status_code == 200
    assert pclient.get("auth/session/").data["status"] == "anonymous"
    p = patient(org)
    relation = f"organizations/{org.id}/patients/{p.id}/relationships/"
    assert b.post(relation, {"professional": str(professional.id)}).status_code == 200
    assert (
        b.post(relation, {"professional": str(professional.id), "active": False}).status_code == 200
    )
    assert not CareRelationship.objects.get(patient=p).active
    missing = user("unverified@patients.example", verified=False)
    assert b.post(path, {"email": missing.email, "role": "professional"}).status_code == 400
    target = user("plain@patients.example")
    assert b.post(path, {"email": target.email, "role": "admin"}).status_code == 400
    assert b.post(path, {"email": target.email, "role": "researcher"}).status_code == 400
    assert b.post(path, {"email": target.email, "role": "professional"}).status_code == 400
    assert b.post(relation, {"professional": str(target.id)}).status_code == 403
    assert (
        b.post(
            path, {"email": professional.email, "role": "professional", "active": False}
        ).status_code
        == 200
    )


def test_patient_link_requires_both_verified_identity_and_current_relationship():
    professional = user(role="professional")
    approve(professional)
    b = signed(professional)
    org = org_for(professional)
    p = patient(org, professional)
    target = user("target@patients.example")
    t = signed(target)
    stranger = signed(user("stranger@patients.example"))
    path = f"organizations/{org.id}/patients/{p.id}/link/"
    assert b.post(path, {"email": target.email}).status_code == 202
    token = emailed_token()
    assert stranger.post("patients/link/accept/", {"token": token}).status_code == 403
    assert t.post("patients/link/accept/", {"token": token}).status_code == 200
    assert t.get("patients/").data["count"] == 1
    assert t.get(f"organizations/{org.id}/patients/{p.id}/").status_code == 200
    assert b.post(path, {"email": target.email}).status_code == 400
    assert t.post(path, {"email": target.email}).status_code == 403
    p2 = patient(org, professional)
    assert (
        b.post(
            f"organizations/{org.id}/patients/{p2.id}/link/", {"email": target.email}
        ).status_code
        == 202
    )
    token = emailed_token()
    CareRelationship.objects.filter(patient=p2).update(active=False)
    assert t.post("patients/link/accept/", {"token": token}).status_code == 404


def test_seed_import_dryrun_idempotency_and_fail_closed(tmp_path):
    call_command("seed_demo")
    call_command("seed_demo")
    assert Patient.objects.count() == 3 and User.objects.count() == 0
    org = Organization.objects.first()
    manifest = tmp_path / "patients.json"
    mapping = tmp_path / "map.json"
    rows = [
        {
            "id": "p1",
            "owner": "legacy",
            "kind": "patients",
            "payload": {
                "firstName": "Fittizio",
                "lastName": "Demo",
                "birthDate": "1990-01-01",
                "email": "synthetic@patients.example",
                "privacy": True,
                "notes": "NOT_IMPORTED",
                "cf": "",
            },
        }
    ]
    manifest.write_text(json.dumps(rows))
    mapping.write_text(json.dumps({"legacy": str(org.id)}))
    output = io.StringIO()
    call_command(
        "import_legacy_patients", str(manifest), str(mapping), source="export-1", stdout=output
    )
    assert Patient.objects.count() == 3
    for _ in range(2):
        call_command(
            "import_legacy_patients", str(manifest), str(mapping), source="export-1", apply=True
        )
    imported = Patient.objects.get(legacy_source="export-1")
    assert (
        imported.account is None
        and "privacy" not in imported.demographics
        and "notes" not in imported.demographics
    )
    assert Patient.objects.count() == 4
    rows.append(rows[0])
    manifest.write_text(json.dumps(rows))
    with pytest.raises(CommandError):
        call_command(
            "import_legacy_patients", str(manifest), str(mapping), source="export-2", apply=True
        )
    assert Patient.objects.count() == 4
    manifest.write_text("invalid")
    with pytest.raises(CommandError):
        call_command("import_legacy_patients", str(manifest), str(mapping), source="x")


def test_audit_database_rejects_mutation_and_schema_requires_auth():
    account = user()
    event = AuditEvent.objects.create(actor=account, action="test")
    for operation in ("update", "delete"):
        with pytest.raises(DatabaseError), transaction.atomic():
            query = AuditEvent.objects.filter(pk=event.pk)
            query.update(action="modified") if operation == "update" else query.delete()
    assert Browser().get("schema/").status_code == 403
    assert signed(account).get("schema/").status_code == 200


def test_mfa_reset_cannot_be_used_without_second_factor():
    account = user(role="professional")
    b = signed(account, mfa=False)
    _, _, codes = enroll(b)
    b.post("auth/logout/", {})
    b.post("auth/login/", {"email": account.email, "password": PASSWORD})
    assert b.post("auth/mfa/reset/", {"password": PASSWORD}).status_code == 403
    assert consume_recovery(account, codes[0])
    assert not consume_recovery(account, codes[0])


def test_bootstrap_admin_no_repromotion():
    with patch("getpass.getpass", return_value=PASSWORD):
        call_command("bootstrap_admin", "bootstrap@patients.example")
    admin = User.objects.get(email="bootstrap@patients.example")
    assert admin.is_staff and admin.requires_mfa and not admin.mfa_enabled
    with pytest.raises(CommandError):
        call_command("bootstrap_admin", admin.email)
    with patch("getpass.getpass", side_effect=[PASSWORD, "different"]), pytest.raises(CommandError):
        call_command("bootstrap_admin", "mismatch@patients.example")


def test_english_email_and_disabled_seed(settings):
    account = user()
    account.locale = "en"
    account.save()
    issue_token(account, "verify")
    assert "Expires in 30 minutes" in mail.outbox[-1].body
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_demo")


@pytest.mark.django_db(transaction=True)
def test_concurrent_second_factor_consumption():
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections

    from identity.security import consume_totp

    account = user(role="professional")
    secret = pyotp.random_base32()
    account.mfa_secret = cipher().encrypt(secret.encode()).decode()
    account.mfa_enabled = True
    account.save()
    code = pyotp.TOTP(secret).now()

    def verify(_):
        close_old_connections()
        try:
            return consume_totp(User.objects.get(pk=account.pk), code)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(verify, range(2))) == [False, True]

    RecoveryCode.objects.create(user=account, digest=digest("synthetic-recovery"))

    def recover(_):
        close_old_connections()
        try:
            return consume_recovery(User.objects.get(pk=account.pk), "synthetic-recovery")
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(recover, range(2))) == [False, True]


def test_multiple_profiles_require_mfa_even_after_switching_to_patient():
    account = user()
    b = signed(account)
    assert b.post("auth/profiles/", {"role": "admin"}).status_code == 400
    assert b.post("auth/profiles/", {"role": "professional"}).status_code == 200
    assert b.get("auth/session/").data["status"] == "anonymous"
    account.refresh_from_db()
    assert account.has_profile("patient") and account.has_profile("professional")
    b = signed(account, mfa=False)
    assert b.get("patients/").status_code == 403
    enroll(b)
    assert b.post("auth/profiles/", {"role": "patient"}).status_code == 200
    account.refresh_from_db()
    assert account.requires_mfa
    assert sorted(
        b.post("auth/login/", {"email": account.email, "password": PASSWORD}).data["profiles"]
    ) == ["patient", "professional"]
    assert b.get("patients/").status_code == 403
