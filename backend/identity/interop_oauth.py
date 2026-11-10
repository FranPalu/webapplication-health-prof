"""SMART patient read/search scope gate with delegated RFC 7662 introspection.

No OAuth authorization server or JWT verifier is simulated here. Tokens are
accepted only from a configured HTTPS introspection service and an active,
explicit patient grant bound to the tenant and preapproved application.
"""

import base64
import json
import math
import re
import ssl
from datetime import timedelta
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import APIException, AuthenticationFailed, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from identity.analysis import adult_cutoff
from identity.interop_policy import enabled, require_enabled
from identity.models import (
    InteropApplication,
    InteropApplicationRevocation,
    InteropGrant,
    InteropGrantRevocation,
    Membership,
    Patient,
    ResearchAccessRequest,
    User,
)
from identity.security import Ready, audit, rate_limit
from identity.views import InputView

CONSENT_VERSION = 1
RESOURCES = ("Patient", "DocumentReference", "DiagnosticReport", "Observation", "Consent")
SCOPES = tuple(f"patient/{name}.{mode}" for name in RESOURCES for mode in ("r", "s", "rs"))


class IntegrationUnavailable(APIException):
    status_code = 503
    default_detail = "Trusted integration service is unavailable."


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def https_url(value):
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.fragment
        or parts.query
    ):
        raise IntegrationUnavailable()
    return value


def fhir_base():
    return settings.PUBLIC_ORIGIN.rstrip("/") + "/api/v1/fhir"


def introspect(token):
    endpoint = https_url(settings.SMART_INTROSPECTION_URL)
    if not settings.SMART_CLIENT_ID or not settings.SMART_CLIENT_SECRET:
        raise IntegrationUnavailable()
    credential = base64.b64encode(
        (settings.SMART_CLIENT_ID + ":" + settings.SMART_CLIENT_SECRET).encode()
    ).decode()
    request = Request(
        endpoint,
        data=urlencode({"token": token, "token_type_hint": "access_token"}).encode(),
        headers={
            "Authorization": "Basic " + credential,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        opener = build_opener(NoRedirects(), HTTPSHandler(context=ssl.create_default_context()))
        with opener.open(request, timeout=5) as response:
            data = response.read(65537)
        if len(data) > 65536:
            raise ValueError("Response limit")
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError("Invalid response")
        return result
    except (OSError, ValueError) as exc:
        raise IntegrationUnavailable() from exc


def verified_claims(request):
    header = get_authorization_header(request)
    if not header:
        return None
    if not enabled() or not re.fullmatch(rb"Bearer [A-Za-z0-9._~+/-]{20,4096}=*", header):
        raise AuthenticationFailed("Invalid bearer authorization.")
    rate_limit(request, "interop-token", limit=60)
    result = introspect(header[7:].decode("ascii"))
    expiration = result.get("exp")
    if (
        result.get("active") is not True
        or result.get("iss") != settings.SMART_ISSUER
        or not settings.SMART_ISSUER
        or result.get("aud") != fhir_base()
        or not isinstance(expiration, (int, float))
        or isinstance(expiration, bool)
        or not math.isfinite(expiration)
        or expiration <= timezone.now().timestamp()
        or not isinstance(result.get("token_type", "Bearer"), str)
        or result.get("token_type", "Bearer").lower() != "bearer"
    ):
        raise AuthenticationFailed("Inactive or incorrectly bound token.")
    return result


class SmartBearerAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return 'Bearer realm="fhir"'

    def authenticate(self, request):
        result = verified_claims(request)
        if result is None:
            return None
        try:
            actor = User.objects.get(
                pk=result.get("sub"), is_active=True, email_verified=True, role="patient"
            )
            grant = InteropGrant.objects.select_related("patient__organization", "application").get(
                pk=result.get("grant_id"),
                grantor=actor,
                patient__account=actor,
                application__organization_id=result.get("tenant"),
                patient__organization_id=result.get("tenant"),
                application__client_id=result.get("client_id"),
                expires_at__gt=timezone.now(),
                interopgrantrevocation__isnull=True,
                application__interopapplicationrevocation__isnull=True,
                consent_version=CONSENT_VERSION,
                patient__birth_date__lte=adult_cutoff(),
            )
        except (
            User.DoesNotExist,
            InteropGrant.DoesNotExist,
            ValueError,
            TypeError,
            serializers.ValidationError,
            DjangoValidationError,
        ) as exc:
            raise AuthenticationFailed("Patient grant unavailable.") from exc
        if result.get("auth_version") != actor.auth_version or str(grant.patient_id) != result.get(
            "patient"
        ):
            raise AuthenticationFailed("Patient context changed.")
        scopes = result.get("scope", "")
        if (
            not isinstance(scopes, str)
            or not scopes
            or not set(scopes.split()) <= set(grant.scopes)
        ):
            raise AuthenticationFailed("Unapproved scope.")
        audit(actor, "interop.token_used", grant.pk, grant.patient.organization)
        return actor, {"grant": grant, "scopes": set(scopes.split())}


def enforce_scope(request, resource, action, patient_id=None):
    if not isinstance(request.auth, dict) or "grant" not in request.auth:
        return
    grant = request.auth["grant"]
    if (
        resource not in RESOURCES
        or action not in ("r", "s")
        or not any(
            scope == f"patient/{resource}.{mode}"
            for scope in request.auth["scopes"]
            for mode in (action, "rs")
        )
    ):
        raise PermissionDenied("Scope does not permit this interaction.")
    if patient_id is not None and str(grant.patient_id) != str(patient_id):
        raise PermissionDenied("Patient compartment mismatch.")


class ApplicationInput(serializers.Serializer):
    client_id = serializers.RegexField(r"^[A-Za-z0-9._-]{1,120}$")


class ReasonInput(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


def organization_admin(request, organization_id):
    require_enabled()
    if request.session.get("mfa_version") != request.user.auth_version:
        raise PermissionDenied()
    return get_object_or_404(
        Membership, organization_id=organization_id, user=request.user, role="admin", active=True
    )


class InteropApplicationsView(InputView):
    serializer_class = ApplicationInput

    @extend_schema(responses={201: OpenApiTypes.OBJECT})
    @transaction.atomic
    def post(self, request, org_id):
        member = organization_admin(request, org_id)
        application, _ = InteropApplication.objects.get_or_create(
            organization=member.organization,
            client_id=self.data(request)["client_id"],
            defaults={"author": request.user},
        )
        audit(request.user, "interop.application_registered", application.pk, member.organization)
        return Response({"id": application.pk}, status=201)


class ApplicationRevocationView(InputView):
    serializer_class = ReasonInput

    @extend_schema(responses={204: None})
    @transaction.atomic
    def post(self, request, org_id, application_id):
        organization_admin(request, org_id)
        app = get_object_or_404(
            InteropApplication.objects.select_for_update(of=("self",)),
            pk=application_id,
            organization_id=org_id,
        )
        InteropApplicationRevocation.objects.get_or_create(
            application=app, defaults={"actor": request.user, **self.data(request)}
        )
        audit(request.user, "interop.application_revoked", app.pk, app.organization)
        return Response(status=204)


class GrantInput(serializers.Serializer):
    application = serializers.UUIDField()
    scopes = serializers.ListField(
        child=serializers.ChoiceField(choices=SCOPES), min_length=1, max_length=15
    )
    expires_at = serializers.DateTimeField()
    consent_version = serializers.IntegerField(min_value=CONSENT_VERSION, max_value=CONSENT_VERSION)
    confirmed = serializers.BooleanField()

    def validate(self, data):
        if (
            not data["confirmed"]
            or len(set(data["scopes"])) != len(data["scopes"])
            or not timezone.now() < data["expires_at"] <= timezone.now() + timedelta(days=90)
        ):
            raise serializers.ValidationError(
                "Explicit current, bounded patient authorization is required."
            )
        return data


class InteropGrantView(InputView):
    serializer_class = GrantInput

    @extend_schema(responses={201: OpenApiTypes.OBJECT})
    @transaction.atomic
    def post(self, request, patient_id):
        require_enabled()
        rate_limit(request, "interop-grant", limit=24, by_user=True)
        patient = get_object_or_404(
            Patient.objects.select_for_update(),
            pk=patient_id,
            account=request.user,
            birth_date__lte=adult_cutoff(),
        )
        data = self.data(request)
        app = get_object_or_404(
            InteropApplication.objects.select_for_update(of=("self",)),
            pk=data.pop("application"),
            organization=patient.organization,
            interopapplicationrevocation__isnull=True,
        )
        data.pop("confirmed")
        grant = InteropGrant.objects.create(
            application=app, patient=patient, grantor=request.user, **data
        )
        audit(request.user, "interop.grant_created", grant.pk, patient.organization)
        return Response({"id": grant.pk}, status=201)


class GrantRevocationView(InputView):
    serializer_class = ReasonInput

    @extend_schema(responses={204: None})
    @transaction.atomic
    def post(self, request, grant_id):
        require_enabled()
        grant = get_object_or_404(
            InteropGrant.objects.select_for_update(), pk=grant_id, grantor=request.user
        )
        InteropGrantRevocation.objects.get_or_create(
            grant=grant, defaults={"actor": request.user, **self.data(request)}
        )
        audit(request.user, "interop.grant_revoked", grant.pk, grant.patient.organization)
        return Response(status=204)


class SmartDiscoveryView(InputView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        if (
            not enabled()
            or not settings.SMART_INTROSPECTION_URL
            or not settings.SMART_CLIENT_SECRET
        ):
            raise IntegrationUnavailable()
        return JsonResponse(
            {
                "issuer": https_url(settings.SMART_ISSUER),
                "authorization_endpoint": https_url(settings.SMART_AUTHORIZATION_URL),
                "token_endpoint": https_url(settings.SMART_TOKEN_URL),
                "grant_types_supported": ["authorization_code"],
                "response_types_supported": ["code"],
                "code_challenge_methods_supported": ["S256"],
                "scopes_supported": list(SCOPES) + ["user/MeasureReport.rs"],
                "capabilities": ["permission-patient", "permission-user", "permission-v2"],
            }
        )


class SmartResearchAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return 'Bearer realm="research-export"'

    def authenticate(self, request):
        claims = verified_claims(request)
        if claims is None:
            return None
        auth_time = claims.get("auth_time")
        if (
            claims.get("scope") != "user/MeasureReport.rs"
            or not isinstance(claims.get("amr"), list)
            or "mfa" not in claims["amr"]
            or not isinstance(auth_time, (int, float))
            or isinstance(auth_time, bool)
            or not math.isfinite(auth_time)
            or not timezone.now().timestamp() - 3600 <= auth_time <= timezone.now().timestamp()
        ):
            raise AuthenticationFailed("Fresh MFA and a bounded research scope are required.")
        try:
            actor = User.objects.get(
                pk=claims.get("sub"), is_active=True, email_verified=True, mfa_enabled=True
            )
            access = ResearchAccessRequest.objects.get(
                pk=claims.get("research_access_request"),
                status="approved",
                organization_id=claims.get("tenant"),
            )
            if (
                actor.auth_version != claims.get("auth_version")
                or not Membership.objects.filter(
                    user=actor,
                    organization=access.organization,
                    role="admin",
                    active=True,
                    organization__kind="research",
                ).exists()
                or not InteropApplication.objects.filter(
                    organization=access.organization,
                    client_id=claims.get("client_id"),
                    interopapplicationrevocation__isnull=True,
                ).exists()
            ):
                raise AuthenticationFailed("Research authorization unavailable.")
        except (
            User.DoesNotExist,
            ResearchAccessRequest.DoesNotExist,
            DjangoValidationError,
            ValueError,
            TypeError,
        ) as exc:
            raise AuthenticationFailed("Research authorization unavailable.") from exc
        audit(actor, "interop.research_token_used", access.pk, access.organization)
        return actor, {"research_access": access.pk}


class ResearchInteropReady(Ready):
    def has_permission(self, request, view):
        if isinstance(request.auth, dict) and "research_access" in request.auth:
            return bool(
                request.user.is_active and request.user.email_verified and request.user.mfa_enabled
            )
        return super().has_permission(request, view)
