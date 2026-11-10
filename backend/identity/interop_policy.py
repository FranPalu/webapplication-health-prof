"""Fail-closed P5 feature boundary; no production integration is implied."""

from django.conf import settings
from rest_framework.exceptions import PermissionDenied


def enabled():
    return settings.DEBUG and settings.FHIR_INTEROP_ENABLED


def require_enabled():
    if not enabled():
        raise PermissionDenied("Interoperability is disabled outside synthetic testing.")
