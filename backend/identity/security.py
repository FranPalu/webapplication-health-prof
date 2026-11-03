import hashlib
import secrets
import time
from datetime import timedelta
from typing import cast

import pyotp
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import logout
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied, Throttled
from rest_framework.permissions import BasePermission

from .models import AuditEvent, RateBucket, RecoveryCode, User


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def cipher() -> Fernet:
    return Fernet(settings.MFA_ENCRYPTION_KEY.encode())


def audit(user, action: str, resource_id="", organization=None) -> None:
    AuditEvent.objects.create(
        actor=user if user and user.is_authenticated else None,
        action=action,
        resource_id=str(resource_id),
        organization=organization,
    )


class StrictSessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        # DRF normally skips CSRF for anonymous requests; login/register must not.
        self.enforce_csrf(request)
        return super().authenticate(request)


class Ready(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user.is_authenticated
            and user.email_verified
            and (
                not user.requires_mfa
                or (user.mfa_enabled and request.session.get("mfa_version") == user.auth_version)
            )
        )


class PlatformAdmin(Ready):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_staff


class SecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            user = cast(User, request.user)
            if request.session.get("auth_version") != user.auth_version:
                logout(request)
        response = self.get_response(request)
        response["Cache-Control"] = "no-store"
        response["X-Frame-Options"] = "DENY"
        response["X-Content-Type-Options"] = "nosniff"
        response["Referrer-Policy"] = "same-origin"
        return response


def exception_handler(exc, context):
    from rest_framework.views import exception_handler as drf_exception_handler

    response = drf_exception_handler(exc, context)
    request = context.get("request")
    if response is not None:
        if response.status_code == 403:
            audit(getattr(request, "user", None), "access.denied")
        response.data = {"code": getattr(exc, "default_code", "invalid"), "detail": response.data}
        return response
    return JsonResponse({"code": "internal_error"}, status=500)


def rate_limit(request, scope: str, limit=30, seconds=300) -> None:
    # Do not trust X-Forwarded-For supplied by a client. Proxy overwrites REMOTE_ADDR via
    # a trusted deployment boundary only. Hash identifiers so no contact/IP is stored.
    key = digest(settings.SECRET_KEY + scope + request.META.get("REMOTE_ADDR", "unknown"))
    now = timezone.now()
    with transaction.atomic():
        RateBucket.objects.get_or_create(
            key=key, defaults={"expires_at": now + timedelta(seconds=seconds)}
        )
        bucket = RateBucket.objects.select_for_update().get(pk=key)
        if bucket.expires_at <= now:
            bucket.count = 0
            bucket.expires_at = now + timedelta(seconds=seconds)
        bucket.count += 1
        bucket.save()
    # Called in non-atomic auth views, so failures cannot roll back the counter.
    if bucket.count > limit:
        raise Throttled(wait=seconds)


@transaction.atomic
def consume_totp(user: User, code: str) -> bool:
    locked = User.objects.select_for_update().get(pk=user.pk)
    if not locked.mfa_secret:
        return False
    totp = pyotp.TOTP(cipher().decrypt(locked.mfa_secret.encode()).decode())
    step = int(time.time()) // 30
    for candidate in (step - 1, step, step + 1):
        if candidate > locked.mfa_last_step and secrets.compare_digest(
            totp.at(candidate * 30), code
        ):
            locked.mfa_last_step = candidate
            locked.save(update_fields=["mfa_last_step"])
            return True
    return False


@transaction.atomic
def consume_recovery(user: User, code: str) -> bool:
    entry = (
        RecoveryCode.objects.select_for_update()
        .filter(user=user, digest=digest(code), used_at=None)
        .first()
    )
    if not entry:
        return False
    entry.used_at = timezone.now()
    entry.save(update_fields=["used_at"])
    audit(user, "mfa.recovery_used")
    return True


def require_platform_admin(request) -> None:
    if not PlatformAdmin().has_permission(request, None):
        raise PermissionDenied()
