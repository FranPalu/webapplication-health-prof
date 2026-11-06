"""Tenant-bound identifiers and independent source confirmation for report intake."""

import re

from django.conf import settings
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils.crypto import salted_hmac
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from identity.clinical import clinical_patients
from identity.models import PatientIdentifier
from identity.security import audit, rate_limit
from identity.serializers import StatusOutput
from identity.services import verified_professional
from identity.views import InputView

# Odd-position lookup from the Italian fiscal-code check-character algorithm.
ODD = (1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23)


def normalized_identifier(kind: str, value: str) -> str:
    if not value.isascii():
        raise ValidationError("Invalid identifier format.")
    value = value.strip().upper()
    if kind == PatientIdentifier.Kind.FACILITY and re.fullmatch(
        r"[A-Z0-9][A-Z0-9._-]{0,63}", value
    ):
        return value
    if kind == PatientIdentifier.Kind.HEALTH_CARD and re.fullmatch(r"[0-9]{20}", value):
        return value
    if kind == PatientIdentifier.Kind.TAX_CODE and re.fullmatch(
        r"[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]",
        value,
    ):
        indices = [ord(char) - ord("A") if char.isalpha() else int(char) for char in value[:15]]
        checksum = sum(ODD[index] if pos % 2 == 0 else index for pos, index in enumerate(indices))
        if value[-1] == chr(ord("A") + checksum % 26):
            return value
    raise ValidationError("Invalid identifier format.")


def fiscal_birth_matches(value, birth_date):
    code = normalized_identifier(PatientIdentifier.Kind.TAX_CODE, value)
    digits = str.maketrans("LMNPQRSTUV", "0123456789")
    year = int(code[6:8].translate(digits))
    month = "ABCDEHLMPRST".index(code[8]) + 1
    day = int(code[9:11].translate(digits))
    return (
        year == birth_date.year % 100
        and month == birth_date.month
        and day in (birth_date.day, birth_date.day + 40)
    )


class IdentificationUnavailable(APIException):
    status_code = 503
    default_detail = "Patient identification is unavailable."


def identifier_digest(organization_id, kind, value):
    if len(settings.CLINICAL_IDENTITY_KEY) < 32:
        raise IdentificationUnavailable()
    normalized = normalized_identifier(kind, value)
    return salted_hmac(
        "claria.patient-identifier.v1",
        f"{organization_id}:{kind}:{normalized}",
        secret=settings.CLINICAL_IDENTITY_KEY,
        algorithm="sha256",
    ).hexdigest()


class IdentifierInput(serializers.Serializer):
    identifier_kind = serializers.ChoiceField(choices=PatientIdentifier.Kind.choices)
    identifier_value = serializers.CharField(max_length=64)
    source_birth_date = serializers.DateField()


def confirm_report_patient(patient, data):
    kind = data.get("identifier_kind")
    value = data.get("identifier_value")
    if (
        not kind
        or not value
        or data.get("source_birth_date") != patient.birth_date
        or not PatientIdentifier.objects.filter(
            patient=patient,
            organization_id=patient.organization_id,
            kind=kind,
            digest=identifier_digest(patient.organization_id, kind, value),
        ).exists()
    ):
        raise ValidationError("Two source identifiers are required and must match the patient.")


class PatientIdentifierView(InputView):
    serializer_class = IdentifierInput

    @extend_schema(responses={201: StatusOutput})
    def post(self, request, patient_id):
        if not verified_professional(request.user):
            raise PermissionDenied()
        rate_limit(request, "patient-identifier-enrollment", limit=12, by_user=True)
        patient = get_object_or_404(clinical_patients(request.user), pk=patient_id)
        data = self.data(request)
        if patient.birth_date != data["source_birth_date"]:
            raise ValidationError("Identifier cannot be enrolled.")
        kind = data["identifier_kind"]
        if kind == PatientIdentifier.Kind.TAX_CODE and not fiscal_birth_matches(
            data["identifier_value"], patient.birth_date
        ):
            raise ValidationError("Identifier cannot be enrolled.")
        digest = identifier_digest(patient.organization_id, kind, data["identifier_value"])
        try:
            with transaction.atomic():
                PatientIdentifier.objects.create(
                    patient=patient,
                    organization_id=patient.organization_id,
                    kind=kind,
                    digest=digest,
                    recorded_by=request.user,
                )
                audit(
                    request.user, "clinical.identifier_enrolled", patient.pk, patient.organization
                )
        except IntegrityError as exc:
            raise ValidationError("Identifier cannot be enrolled.") from exc
        return self.status("recorded", 201)
