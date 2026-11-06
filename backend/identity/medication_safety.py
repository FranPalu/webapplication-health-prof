"""Deterministic medication screening with a deployment-owned evidence provider."""

from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations
from typing import Protocol

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.module_loading import import_string
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from identity.clinical import clinical_patients
from identity.clinical_safety import LabAcknowledgmentInput, require_enabled
from identity.models import MedicationSafetyCheck, MedicationSafetyOverride
from identity.patient_identification import IdentifierInput, confirm_report_patient
from identity.security import audit, rate_limit
from identity.services import verified_professional
from identity.views import InputView, StatusOutput


@dataclass(frozen=True)
class Medication:
    code: str
    route: str
    unit: str
    daily_dose: Decimal


@dataclass(frozen=True)
class DrugFacts:
    ingredients: frozenset[str]
    therapy_groups: frozenset[str]
    maximum_daily_dose: Decimal
    unit: str


@dataclass(frozen=True)
class Evidence:
    reference: str
    level: str


@dataclass(frozen=True)
class MedicationSnapshot:
    source: str
    version: str
    license_reference: str
    evidence: Evidence
    complete_for_context: bool
    drugs: dict[tuple[str, str], DrugFacts]
    interactions: dict[frozenset[str], Evidence]
    contraindications: dict[tuple[str, str], Evidence]


class MedicationSourceUnavailable(Exception):
    """The adapter cannot obtain evidence for this screening."""


class MedicationProvider(Protocol):
    def snapshot(
        self,
        *,
        medications: tuple[Medication, ...],
        allergies: frozenset[str],
        conditions: frozenset[str],
    ) -> MedicationSnapshot: ...


def configured_provider() -> MedicationProvider | None:
    path = settings.CLINICAL_MEDICATION_PROVIDER
    return import_string(path)() if path else None


def evaluate_medications(
    medications: tuple[Medication, ...],
    allergies: frozenset[str],
    conditions: frozenset[str],
    snapshot: MedicationSnapshot | None,
) -> dict[str, object]:
    unavailable: dict[str, object] = {"status": "insufficient", "source": None, "findings": []}
    if snapshot is None or not all(
        (
            snapshot.source,
            snapshot.version,
            snapshot.license_reference,
            snapshot.evidence.reference,
            snapshot.evidence.level,
        )
    ):
        return unavailable

    findings = []
    complete = snapshot.complete_for_context

    def add(kind, codes, evidence):
        nonlocal complete
        if not evidence.reference or not evidence.level:
            complete = False
            return
        findings.append(
            {
                "kind": kind,
                "medications": list(codes),
                "reference": evidence.reference,
                "evidence_level": evidence.level,
            }
        )

    facts = []
    for medication in medications:
        drug = snapshot.drugs.get((medication.code, medication.route))
        facts.append(drug)
        if drug is None:
            complete = False
        else:
            if (
                medication.unit != drug.unit
                or not drug.maximum_daily_dose.is_finite()
                or drug.maximum_daily_dose <= 0
            ):
                complete = False
            elif medication.daily_dose > drug.maximum_daily_dose:
                add("maximum_dose", (medication.code,), snapshot.evidence)
            if not drug.ingredients or not drug.therapy_groups:
                complete = False
            if allergies & drug.ingredients:
                add("allergy", (medication.code,), snapshot.evidence)
        for condition in sorted(conditions):
            evidence = snapshot.contraindications.get((medication.code, condition))
            if evidence:
                add("contraindication", (medication.code,), evidence)

    for left, right in combinations(range(len(medications)), 2):
        first, second = medications[left].code, medications[right].code
        evidence = snapshot.interactions.get(frozenset((first, second)))
        if evidence:
            add("interaction", (first, second), evidence)
        a, b = facts[left], facts[right]
        if first == second or (
            a and b and (a.ingredients & b.ingredients or a.therapy_groups & b.therapy_groups)
        ):
            add("duplication", (first, second), snapshot.evidence)

    return {
        "status": ("findings" if findings else "no_findings") if complete else "insufficient",
        "source": {
            "name": snapshot.source,
            "version": snapshot.version,
            "license": snapshot.license_reference,
            "reference": snapshot.evidence.reference,
            "evidence_level": snapshot.evidence.level,
        },
        "findings": findings,
    }


class MedicationItemInput(serializers.Serializer):
    code = serializers.CharField(max_length=64)
    route = serializers.CharField(max_length=32)
    unit = serializers.CharField(max_length=32, trim_whitespace=False)
    daily_dose = serializers.DecimalField(
        max_digits=14, decimal_places=6, min_value=Decimal("0.000001")
    )


class MedicationSafetyInput(IdentifierInput):
    context_confirmed = serializers.BooleanField(default=False)
    medications = MedicationItemInput(many=True, allow_empty=False)
    allergies = serializers.ListField(child=serializers.CharField(max_length=64), max_length=50)
    conditions = serializers.ListField(child=serializers.CharField(max_length=64), max_length=50)

    def validate_medications(self, value):
        if len(value) > 20:
            raise ValidationError("At most 20 medications are allowed.")
        return value


class MedicationEvidenceOutput(serializers.Serializer):
    name = serializers.CharField()
    version = serializers.CharField()
    license = serializers.CharField()
    reference = serializers.CharField()
    evidence_level = serializers.CharField()


class MedicationFindingOutput(serializers.Serializer):
    kind = serializers.CharField()
    medications = serializers.ListField(child=serializers.CharField())
    reference = serializers.CharField()
    evidence_level = serializers.CharField()


class MedicationResultOutput(serializers.Serializer):
    status = serializers.CharField()
    # DRF removes declared fields from the class before Field.source is initialized.
    source = MedicationEvidenceOutput(allow_null=True)  # type: ignore[assignment]
    findings = MedicationFindingOutput(many=True)


class MedicationSafetyOutput(serializers.ModelSerializer):
    result = MedicationResultOutput(read_only=True)

    class Meta:
        model = MedicationSafetyCheck
        fields = ("id", "result", "created_at")


class MedicationSafetyView(InputView):
    serializer_class = MedicationSafetyInput

    @extend_schema(responses={201: MedicationSafetyOutput})
    def post(self, request, patient_id):
        require_enabled()
        if not verified_professional(request.user):
            raise PermissionDenied()
        rate_limit(request, "clinical-medication-safety", limit=24, by_user=True)
        patient = get_object_or_404(clinical_patients(request.user), pk=patient_id)
        data = self.data(request)
        confirm_report_patient(patient, data)
        medications = tuple(Medication(**item) for item in data["medications"])
        allergies, conditions = frozenset(data["allergies"]), frozenset(data["conditions"])
        provider = configured_provider()
        try:
            snapshot = (
                provider.snapshot(
                    medications=medications, allergies=allergies, conditions=conditions
                )
                if provider and data["context_confirmed"]
                else None
            )
        except MedicationSourceUnavailable:
            snapshot = None
        result = evaluate_medications(medications, allergies, conditions, snapshot)
        with transaction.atomic():
            patient = get_object_or_404(clinical_patients(request.user), pk=patient_id)
            check = MedicationSafetyCheck.objects.create(
                patient=patient, author=request.user, result=result
            )
            audit(request.user, "clinical.medication_screened", check.pk, patient.organization)
        return Response(MedicationSafetyOutput(check).data, status=201)


class OverrideInput(LabAcknowledgmentInput):
    reason = serializers.CharField(max_length=500)


class MedicationOverrideView(InputView):
    serializer_class = OverrideInput

    @extend_schema(responses=StatusOutput)
    @transaction.atomic
    def post(self, request, check_id):
        require_enabled()
        if not verified_professional(request.user):
            raise PermissionDenied()
        check = get_object_or_404(
            MedicationSafetyCheck.objects.select_for_update(of=("self",)).select_related(
                "patient__organization"
            ),
            pk=check_id,
            author=request.user,
            patient__in=clinical_patients(request.user),
        )
        data = self.data(request)
        if data["patient"] != check.patient_id or check.result.get("status") != "findings":
            raise ValidationError(
                "Only a complete finding for the confirmed patient can be overridden."
            )
        _, created = MedicationSafetyOverride.objects.get_or_create(
            screening=check, defaults={"actor": request.user, "reason": data["reason"]}
        )
        if created:
            audit(
                request.user,
                "clinical.medication_override_recorded",
                check.pk,
                check.patient.organization,
            )
        return self.status("recorded")
