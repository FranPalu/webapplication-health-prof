"""Synthetic-only review queue and tenant-approved laboratory alert rules."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Literal

from django.conf import settings
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from identity.clinical import clinical_patients
from identity.clinical_terminology import OBSERVATION_UNITS
from identity.models import (
    LabAlertRule,
    LabAlertRuleApproval,
    LabResultReview,
    Membership,
    Organization,
    User,
)
from identity.security import audit, rate_limit
from identity.services import verified_professional
from identity.views import InputView, notify_user_id

Outcome = Literal["critical", "within_limits", "insufficient"]
COHORT = ("code", "laboratory", "sex", "min_age", "max_age")


@dataclass(frozen=True)
class Limits:
    unit: str
    low: Decimal | None
    high: Decimal | None


def evaluate(value: Decimal, unit: str, limits: Limits | None) -> Outcome:
    if limits is None or limits.unit != unit or not value.is_finite():
        return "insufficient"
    low, high = limits.low, limits.high
    if (low is None and high is None) or any(
        bound is not None and not bound.is_finite() for bound in (low, high)
    ):
        return "insufficient"
    if low is not None and high is not None and low >= high:
        return "insufficient"
    if (limits.low is not None and value <= limits.low) or (
        limits.high is not None and value >= limits.high
    ):
        return "critical"
    return "within_limits"


def enabled() -> bool:
    return settings.DEBUG and settings.CLINICAL_SAFETY_ENABLED


def require_enabled():
    if not enabled():
        raise Http404


def tenant_clinician(user, organization_id, *, admin=False):
    if not (user.is_active and user.email_verified and verified_professional(user)):
        return False
    members = Membership.objects.filter(user=user, organization_id=organization_id, active=True)
    return members.filter(role="admin").exists() if admin else members.exists()


def current_rules(organization_id):
    rows = (
        LabAlertRule.objects.filter(
            organization_id=organization_id, labalertruleapproval__isnull=False
        )
        .order_by(*COHORT, "-version")
        .distinct(*COHORT)
    )
    return [rule for rule in rows if rule.enabled]


def matching_rule(rules, observation, age, sex):
    laboratory = observation.reference_range.get("laboratory")
    candidates = [
        rule
        for rule in rules
        if rule.code == observation.code
        and rule.laboratory == laboratory
        and rule.min_age <= age <= rule.max_age
    ]
    if not sex and any(rule.sex for rule in candidates):
        return None
    matches = [rule for rule in candidates if not rule.sex or rule.sex == sex]
    return matches[0] if len(matches) == 1 else None


def create_review(report):
    if not enabled():
        return
    patient = report.patient
    born = patient.birth_date
    at = timezone.localdate(report.effective_at)
    age = at.year - born.year - ((at.month, at.day) < (born.month, born.day))
    rules = current_rules(patient.organization_id)
    outcomes = []
    critical = []
    for observation in report.observations.order_by("pk"):
        rule = matching_rule(rules, observation, age, report.evaluation_sex)
        limits = Limits(rule.unit, rule.low, rule.high) if rule else None
        outcome = evaluate(observation.value, observation.unit, limits)
        outcomes.append(
            {
                "observation": str(observation.pk),
                "rule": str(rule.pk) if rule else None,
                "outcome": outcome,
            }
        )
        if outcome == "critical" and rule:
            critical.append(rule)
    shortest = min(critical, key=lambda rule: (rule.sla_minutes, rule.pk), default=None)
    outcome = (
        "critical"
        if shortest
        else "insufficient"
        if any(row["outcome"] == "insufficient" for row in outcomes)
        else "within_limits"
    )
    review = LabResultReview.objects.create(
        report=report,
        outcome=outcome,
        findings=outcomes,
        backup=shortest.backup if shortest else None,
        due_at=timezone.now() + timedelta(minutes=shortest.sla_minutes) if shortest else None,
    )
    audit(report.author, "clinical.result_review_queued", review.pk, patient.organization)
    if shortest:
        notify_user_id(report.author_id, "clinical.result_attention", review.pk)


def escalate_due(now):
    if not enabled():
        return 0
    ids = list(
        LabResultReview.objects.filter(
            due_at__lte=now, escalated_at__isnull=True, acknowledged_at__isnull=True
        )
        .order_by("due_at", "pk")
        .values_list("pk", flat=True)[:100]
    )
    count = 0
    for pk in ids:
        with transaction.atomic():
            review = (
                LabResultReview.objects.select_for_update(of=("self",))
                .select_related("report__patient__organization", "backup")
                .filter(pk=pk, escalated_at__isnull=True, acknowledged_at__isnull=True)
                .first()
            )
            if review is None:
                continue
            patient = review.report.patient
            backup = review.backup
            deliverable = (
                backup is not None
                and backup.pk != review.report.author_id
                and backup.is_active
                and backup.email_verified
                and clinical_patients(backup).filter(pk=patient.pk).exists()
            )
            if deliverable and backup is not None:
                notify_user_id(backup.pk, "clinical.result_escalated", review.pk)
            audit(
                None,
                "clinical.result_escalated"
                if deliverable
                else "clinical.result_escalation_unassigned",
                review.pk,
                patient.organization,
            )
            review.escalated_at = now
            review.escalation_assigned = deliverable
            review.save(update_fields=["escalated_at", "escalation_assigned"])
            count += 1
    return count


class LabRuleInput(serializers.Serializer):
    code = serializers.ChoiceField(choices=sorted(OBSERVATION_UNITS))
    unit = serializers.CharField(max_length=32, trim_whitespace=False)
    laboratory = serializers.CharField(max_length=120)
    sex = serializers.ChoiceField(choices=["female", "male"], allow_blank=True, default="")
    min_age = serializers.IntegerField(min_value=18, max_value=130)
    max_age = serializers.IntegerField(min_value=18, max_value=130)
    low = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, allow_null=True)
    high = serializers.DecimalField(
        max_digits=14, decimal_places=6, required=False, allow_null=True
    )
    sla_minutes = serializers.IntegerField(min_value=1, max_value=1440)
    backup = serializers.UUIDField()
    evidence = serializers.CharField(max_length=500)
    enabled = serializers.BooleanField(default=True)

    def validate(self, data):
        low, high = data.get("low"), data.get("high")
        if data["enabled"] and low is None and high is None:
            raise ValidationError("An enabled rule requires at least one critical limit.")
        if low is not None and high is not None and low >= high:
            raise ValidationError("Critical limits must be ordered.")
        if data["min_age"] > data["max_age"] or data["unit"] != OBSERVATION_UNITS[data["code"]]:
            raise ValidationError("Invalid age interval or analyte unit.")
        return data


class LabRuleOutput(serializers.ModelSerializer):
    approved = serializers.SerializerMethodField()

    class Meta:
        model = LabAlertRule
        fields = (
            "id",
            "code",
            "unit",
            "laboratory",
            "sex",
            "min_age",
            "max_age",
            "low",
            "high",
            "sla_minutes",
            "backup",
            "evidence",
            "enabled",
            "version",
            "approved",
        )

    def get_approved(self, instance) -> bool:
        return hasattr(instance, "labalertruleapproval")


class LabRuleView(InputView):
    serializer_class = LabRuleInput

    @extend_schema(responses=LabRuleOutput(many=True))
    def get(self, request, org_id):
        require_enabled()
        if not tenant_clinician(request.user, org_id):
            raise PermissionDenied()
        rows = (
            LabAlertRule.objects.filter(organization_id=org_id)
            .select_related("labalertruleapproval")
            .order_by("-created_at", "-pk")
        )
        return self.get_paginated_response(
            LabRuleOutput(self.paginate_queryset(rows), many=True).data
        )

    @extend_schema(responses={201: LabRuleOutput})
    def post(self, request, org_id):
        require_enabled()
        if not tenant_clinician(request.user, org_id):
            raise PermissionDenied()
        rate_limit(request, "clinical-lab-rule", limit=12, by_user=True)
        data = self.data(request)
        backup = get_object_or_404(User, pk=data.pop("backup"))
        if not tenant_clinician(backup, org_id):
            raise ValidationError("Select a verified clinician from the organization.")
        with transaction.atomic():
            organization = get_object_or_404(Organization.objects.select_for_update(), pk=org_id)
            prior = (
                LabAlertRule.objects.filter(
                    organization=organization, **{key: data[key] for key in COHORT}
                )
                .order_by("-version")
                .first()
            )
            rule = LabAlertRule.objects.create(
                organization=organization,
                author=request.user,
                backup=backup,
                version=prior.version + 1 if prior else 1,
                **data,
            )
            audit(request.user, "clinical.lab_rule_proposed", rule.pk, organization)
        return Response(LabRuleOutput(rule).data, status=201)


class LabRuleApprovalView(InputView):
    serializer_class = LabRuleOutput

    @extend_schema(request=None, responses=LabRuleOutput)
    @transaction.atomic
    def post(self, request, org_id, rule_id):
        require_enabled()
        if not tenant_clinician(request.user, org_id, admin=True):
            raise PermissionDenied()
        rule = get_object_or_404(
            LabAlertRule.objects.select_for_update(), pk=rule_id, organization_id=org_id
        )
        if rule.author_id == request.user.pk:
            raise PermissionDenied("A separate reviewer must approve the rule.")
        _, created = LabAlertRuleApproval.objects.get_or_create(
            rule=rule, defaults={"reviewer": request.user}
        )
        if created:
            audit(request.user, "clinical.lab_rule_approved", rule.pk, rule.organization)
        return Response(LabRuleOutput(rule).data)


class LabReviewOutput(serializers.ModelSerializer):
    report = serializers.SerializerMethodField()
    version = serializers.IntegerField(source="report.version", read_only=True)

    def get_report(self, instance) -> str:
        return str(instance.report.root_id or instance.report_id)

    class Meta:
        model = LabResultReview
        fields = (
            "id",
            "report",
            "version",
            "outcome",
            "findings",
            "created_at",
            "due_at",
            "acknowledged_at",
            "escalated_at",
            "escalation_assigned",
        )


class LabReviewView(InputView):
    serializer_class = LabReviewOutput

    @extend_schema(responses=LabReviewOutput(many=True))
    def get(self, request, patient_id):
        require_enabled()
        if not verified_professional(request.user):
            raise PermissionDenied()
        patient = get_object_or_404(clinical_patients(request.user), pk=patient_id)
        rows = (
            LabResultReview.objects.filter(report__patient=patient, acknowledged_at__isnull=True)
            .select_related("report")
            .order_by("due_at", "created_at", "pk")
        )
        audit(request.user, "clinical.result_review_listed", patient.pk, patient.organization)
        return self.get_paginated_response(
            LabReviewOutput(self.paginate_queryset(rows), many=True).data
        )


class LabAcknowledgmentInput(serializers.Serializer):
    patient = serializers.UUIDField()


class LabReviewAcknowledgmentView(InputView):
    serializer_class = LabAcknowledgmentInput

    @extend_schema(responses=LabReviewOutput)
    @transaction.atomic
    def post(self, request, review_id):
        require_enabled()
        if not verified_professional(request.user):
            raise PermissionDenied()
        review = get_object_or_404(
            LabResultReview.objects.select_for_update(of=("self",)).select_related(
                "report__patient__organization"
            ),
            pk=review_id,
            report__patient__in=clinical_patients(request.user),
        )
        if self.data(request)["patient"] != review.report.patient_id:
            raise ValidationError("Patient confirmation does not match this result.")
        if review.acknowledged_at is None:
            review.acknowledged_at = timezone.now()
            review.acknowledged_by = request.user
            review.save(update_fields=["acknowledged_at", "acknowledged_by"])
            audit(
                request.user,
                "clinical.result_acknowledged",
                review.pk,
                review.report.patient.organization,
            )
        return Response(LabReviewOutput(review).data)
