"""Keep synthetic laboratory requests pending through explicit result review."""

from django.db import transaction
from django.db.models import Exists, OuterRef, Q, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from identity.clinical import clinical_patients
from identity.clinical_safety import LabAcknowledgmentInput, require_enabled
from identity.clinical_terminology import LOINC_SYSTEM, OBSERVATION_UNITS
from identity.clinical_views import FhirJSONRenderer
from identity.models import (
    ClinicalReport,
    LabOrder,
    LabOrderResult,
    LabResultCompletion,
    LabResultReview,
)
from identity.patient_identification import IdentifierInput, confirm_report_patient
from identity.security import audit, rate_limit
from identity.services import verified_professional
from identity.views import InputView, StatusOutput


class LabOrderInput(IdentifierInput):
    code = serializers.ChoiceField(choices=sorted(OBSERVATION_UNITS))
    due_at = serializers.DateTimeField()

    def validate_due_at(self, value):
        if value <= timezone.now():
            raise ValidationError("The result deadline must be in the future.")
        return value


class LabOrderOutput(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()

    class Meta:
        model = LabOrder
        fields = ("id", "code", "status", "overdue", "due_at", "created_at")

    def get_status(self, instance) -> str:
        if getattr(instance, "reviewed", False):
            return "reviewed"
        return "awaiting_review" if getattr(instance, "latest_report", None) else "awaiting_result"

    def get_overdue(self, instance) -> bool:
        return not getattr(instance, "reviewed", False) and instance.due_at <= timezone.now()


def orders_with_status(rows):
    latest = ClinicalReport.objects.filter(
        Q(pk=OuterRef("laborderresult__report_id"))
        | Q(root_id=OuterRef("laborderresult__report_id"))
    ).order_by("-version")
    return (
        rows.annotate(latest_report=Subquery(latest.values("pk")[:1]))
        .annotate(
            reviewed=Exists(
                LabResultCompletion.objects.filter(review__report_id=OuterRef("latest_report"))
            )
        )
        .order_by("due_at", "pk")
    )


def lock_order_for_report(patient, data):
    order_id = data.get("order_id")
    if order_id is None:
        return None
    require_enabled()
    order = get_object_or_404(LabOrder.objects.select_for_update(), pk=order_id, patient=patient)
    if LabOrderResult.objects.filter(order=order).exists():
        raise ValidationError("This request already has a result. Use the correction workflow.")
    validate_order_observations(order, data)
    if data["effective_at"] < order.created_at:
        raise ValidationError("The result predates the request.")
    return order


def validate_order_observations(order, data):
    if not any(item["code"] == order.code for item in data["observations"]):
        raise ValidationError("The result must include the requested analyte.")


class LabOrderView(InputView):
    serializer_class = LabOrderInput

    @extend_schema(responses=LabOrderOutput(many=True))
    def get(self, request, patient_id):
        require_enabled()
        if not verified_professional(request.user):
            raise PermissionDenied()
        patient = get_object_or_404(clinical_patients(request.user), pk=patient_id)
        audit(request.user, "clinical.pending_orders_listed", patient.pk, patient.organization)
        rows = orders_with_status(LabOrder.objects.filter(patient=patient)).filter(reviewed=False)
        return self.get_paginated_response(
            LabOrderOutput(self.paginate_queryset(rows), many=True).data
        )

    @extend_schema(responses={201: LabOrderOutput})
    def post(self, request, patient_id):
        require_enabled()
        if not verified_professional(request.user):
            raise PermissionDenied()
        rate_limit(request, "clinical-lab-order", limit=24, by_user=True)
        data = self.data(request)
        with transaction.atomic():
            patient = get_object_or_404(
                clinical_patients(request.user).select_for_update(of=("self",)), pk=patient_id
            )
            confirm_report_patient(patient, data)
            order = LabOrder.objects.create(
                patient=patient, author=request.user, code=data["code"], due_at=data["due_at"]
            )
            audit(request.user, "clinical.lab_order_created", order.pk, patient.organization)
        return Response(LabOrderOutput(order).data, status=201)


class FhirLabOrderView(InputView):
    renderer_classes = [FhirJSONRenderer]
    serializer_class = LabOrderOutput

    @extend_schema(responses={(200, "application/fhir+json"): OpenApiTypes.OBJECT})
    def get(self, request, resource_id):
        require_enabled()
        if not verified_professional(request.user):
            raise PermissionDenied()
        order = get_object_or_404(
            orders_with_status(
                LabOrder.objects.filter(patient__in=clinical_patients(request.user))
            ).select_related("patient__organization"),
            pk=resource_id,
        )
        audit(request.user, "clinical.fhir_read", order.pk, order.patient.organization)
        return JsonResponse(
            {
                "resourceType": "ServiceRequest",
                "id": str(order.pk),
                "status": "completed" if order.reviewed else "active",
                "intent": "order",
                "code": {"coding": [{"system": LOINC_SYSTEM, "code": order.code}]},
                "subject": {"reference": f"Patient/{order.patient_id}"},
                "requester": {"reference": f"Practitioner/{order.author_id}"},
                "authoredOn": order.created_at.isoformat(),
                "occurrencePeriod": {"end": order.due_at.isoformat()},
            },
            content_type="application/fhir+json",
        )


class LabCompletionInput(LabAcknowledgmentInput):
    note = serializers.CharField(max_length=500)


class LabCompletionView(InputView):
    serializer_class = LabCompletionInput

    @extend_schema(responses=StatusOutput)
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
        data = self.data(request)
        if data["patient"] != review.report.patient_id:
            raise ValidationError("Patient confirmation does not match this result.")
        if review.acknowledged_at is None:
            raise ValidationError("Acknowledge the result before completing its review.")
        _, created = LabResultCompletion.objects.get_or_create(
            review=review, defaults={"reviewer": request.user, "note": data["note"]}
        )
        if created:
            audit(
                request.user,
                "clinical.result_review_completed",
                review.pk,
                review.report.patient.organization,
            )
        return self.status("reviewed")
