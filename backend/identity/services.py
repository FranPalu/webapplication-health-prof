import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.html import format_html
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import (
    AccountToken,
    CareRelationship,
    Membership,
    Patient,
    PatientConsent,
    ProfessionalVerification,
    Share,
)
from .security import audit, digest


def issue_token(user, purpose: str, context=None) -> str:
    raw = secrets.token_urlsafe(32)
    AccountToken.objects.filter(user=user, purpose=purpose, used_at=None).update(
        used_at=timezone.now()
    )
    AccountToken.objects.create(
        user=user,
        purpose=purpose,
        digest=digest(raw),
        expires_at=timezone.now() + timedelta(minutes=30),
        context=context or {},
    )
    link = f"{settings.PUBLIC_ORIGIN}/?action={purpose}#token={raw}"
    body = (
        f"Apri il collegamento per completare la richiesta. Scade tra 30 minuti.\n{link}"
        if user.locale == "it"
        else f"Open this link to complete your request. Expires in 30 minutes.\n{link}"
    )
    label = "Apri il portale Clarìa" if user.locale == "it" else "Open the Clarìa portal"
    send_mail(
        "Clarìa — verifica / verification",
        body,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=format_html('<p><a href="{}">{}</a></p>', link, label),
    )
    return raw


def token_entry(raw: str, purpose: str):
    entry = (
        AccountToken.objects.select_for_update()
        .filter(digest=digest(raw), purpose=purpose, used_at=None, expires_at__gt=timezone.now())
        .first()
    )
    if not entry:
        raise ValidationError("Invalid or expired token")
    entry.used_at = timezone.now()
    entry.save(update_fields=["used_at"])
    return entry


def org_member(user, org):
    return Membership.objects.filter(user=user, organization=org, active=True).first()


def require_org_admin(user, org):
    membership = org_member(user, org)
    if not membership or membership.role != "admin":
        raise PermissionDenied()
    return membership


def verified_professional(user) -> bool:
    return (
        user.has_profile("professional")
        and ProfessionalVerification.objects.filter(user=user, status="approved").exists()
    )


def visible_patients(user, org=None):
    qs = Patient.objects.all()
    if org:
        qs = qs.filter(organization=org)
    own = Q(account=user)
    if not verified_professional(user):
        return qs.filter(own)
    orgs = Membership.objects.filter(user=user, active=True).values("organization_id")
    relationships = CareRelationship.objects.filter(professional=user, active=True).values(
        "patient_id"
    )
    return qs.filter(own | Q(organization_id__in=orgs, id__in=relationships))


def share_recipient_queryset(user):
    org_ids = Membership.objects.filter(
        user=user, active=True, role__in=["professional", "admin"]
    ).values("organization_id")
    recipient = Q(recipient_user=user, patient__account=user)
    if verified_professional(user):
        recipient |= Q(recipient_user=user) | Q(recipient_organization_id__in=org_ids)
    return Share.objects.filter(recipient)


def share_consent_granted(share, minimum_version=1) -> bool:
    latest = (
        PatientConsent.objects.filter(share=share)
        .order_by("-created_at", "-pk")
        .values_list("decision", "text_version__version")
        .first()
    )
    return bool(latest and latest[0] == "granted" and latest[1] >= minimum_version)


def share_is_active(share, minimum_version=1) -> bool:
    now = timezone.now()
    current = share
    child = None
    while current is not None:
        if (
            current.revoked_at is not None
            or (current.expires_at is not None and current.expires_at <= now)
            or not share_consent_granted(current, minimum_version)
        ):
            return False
        if (
            child is not None
            and PatientConsent.objects.filter(
                share=current, decision="revoked", created_at__gte=child.created_at
            ).exists()
        ):
            return False
        child, current = current, current.parent
    return True


def user_is_share_participant(user, share) -> bool:
    if share.granted_by_id == user.pk or share.patient.account_id == user.pk:
        return True
    return share_recipient_queryset(user).filter(pk=share.pk).exists()


@transaction.atomic
def change_membership(user, org, target, role: str, active: bool):
    # Lock the organization so concurrent removals cannot remove all administrators.
    type(org).objects.select_for_update().get(pk=org.pk)
    require_org_admin(user, org)
    if target == user:
        raise ValidationError("Self membership changes are not allowed")
    if not target.email_verified:
        raise ValidationError("Account must verify email first")
    if role == "professional" and not target.has_profile("professional"):
        raise ValidationError("Professional profile required")
    if role == "researcher" and not target.has_profile("researcher"):
        raise ValidationError("Researcher profile required")
    if role == "admin" and not target.mfa_enabled:
        raise ValidationError("MFA enrollment required for administrators")
    result, _ = Membership.objects.update_or_create(
        user=target, organization=org, defaults={"role": role, "active": active}
    )
    # Promotion must invalidate prior sessions, including sessions without MFA.
    target.auth_version += 1
    target.save(update_fields=["auth_version"])
    audit(user, "membership.changed", target.id, org)
    return result
