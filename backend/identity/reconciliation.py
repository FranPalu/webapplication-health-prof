"""Two-person reconciliation preserves each record's access and provenance."""

from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from identity.clinical import clinical_patients
from identity.models import Patient, PatientReconciliation, PatientReconciliationApproval
from identity.patient_identification import IdentifierInput, confirm_report_patient
from identity.security import audit, rate_limit
from identity.services import verified_professional
from identity.views import InputView


class ReconciliationIdentityInput(serializers.Serializer):
    source_identity = IdentifierInput()
    target_identity = IdentifierInput()


class ReconciliationInput(ReconciliationIdentityInput):
    target = serializers.UUIDField()
    link = serializers.BooleanField()
    reason = serializers.CharField(max_length=500)


class ReconciliationOutput(serializers.ModelSerializer):
    approved = serializers.SerializerMethodField()

    class Meta:
        model = PatientReconciliation
        fields = ("id", "source", "target", "link", "reason", "approved", "created_at")

    def get_approved(self, instance) -> bool:
        return hasattr(instance, "patientreconciliationapproval")


def lock_pair(user, source_id, target_id):
    if source_id == target_id:
        raise ValidationError("Select two different patient records.")
    ids = (source_id, target_id)
    records = {
        patient.pk: patient
        for patient in Patient.objects.select_for_update().filter(pk__in=ids).order_by("pk")
    }
    if len(records) != 2 or clinical_patients(user).filter(pk__in=ids).distinct().count() != 2:
        raise Http404
    source, target = records[source_id], records[target_id]
    if source.organization_id != target.organization_id:
        raise Http404
    if source.birth_date != target.birth_date or source.account_id != target.account_id:
        raise ValidationError("Patient records require separate identity review.")
    return source, target


def check_transition(source, target, link):
    ids = (source.pk, target.pk)
    decisions = (
        PatientReconciliationApproval.objects.filter(
            Q(proposal__source_id__in=ids) | Q(proposal__target_id__in=ids)
        )
        .select_related("proposal")
        .order_by("-pk")
    )
    seen = set()
    for decision in decisions:
        proposal = decision.proposal
        pair = frozenset((proposal.source_id, proposal.target_id))
        if pair in seen:
            continue
        seen.add(pair)
        if proposal.link:
            if not link and (proposal.source_id, proposal.target_id) == ids:
                return
            raise ValidationError("An active reconciliation already exists.")
    if not link:
        raise ValidationError("No active reconciliation matches these records.")


class PatientReconciliationView(InputView):
    serializer_class = ReconciliationInput

    @extend_schema(responses=ReconciliationOutput(many=True))
    def get(self, request, patient_id):
        accessible = clinical_patients(request.user)
        patient = get_object_or_404(accessible, pk=patient_id)
        rows = (
            PatientReconciliation.objects.filter(source__in=accessible, target__in=accessible)
            .filter(Q(source_id=patient_id) | Q(target_id=patient_id))
            .select_related("patientreconciliationapproval")
            .order_by("-created_at", "-pk")
        )
        audit(request.user, "clinical.reconciliation_listed", patient.pk, patient.organization)
        return self.get_paginated_response(
            ReconciliationOutput(self.paginate_queryset(rows), many=True).data
        )

    @extend_schema(responses={201: ReconciliationOutput})
    def post(self, request, patient_id):
        if not verified_professional(request.user):
            raise PermissionDenied()
        rate_limit(request, "patient-reconciliation", limit=12, by_user=True)
        data = self.data(request)
        with transaction.atomic():
            source, target = lock_pair(request.user, patient_id, data["target"])
            confirm_report_patient(source, data["source_identity"])
            confirm_report_patient(target, data["target_identity"])
            check_transition(source, target, data["link"])
            proposal = PatientReconciliation.objects.create(
                source=source,
                target=target,
                proposer=request.user,
                link=data["link"],
                reason=data["reason"],
            )
            audit(
                request.user, "clinical.reconciliation_proposed", proposal.pk, source.organization
            )
        return Response(ReconciliationOutput(proposal).data, status=201)


class PatientReconciliationApprovalView(InputView):
    serializer_class = ReconciliationIdentityInput

    @extend_schema(responses={200: ReconciliationOutput})
    @transaction.atomic
    def post(self, request, reconciliation_id):
        if not verified_professional(request.user):
            raise PermissionDenied()
        proposal = get_object_or_404(
            PatientReconciliation.objects.select_for_update(), pk=reconciliation_id
        )
        source, target = lock_pair(request.user, proposal.source_id, proposal.target_id)
        if proposal.proposer_id == request.user.pk:
            raise PermissionDenied("A separate reviewer must approve the reconciliation.")
        data = self.data(request)
        confirm_report_patient(source, data["source_identity"])
        confirm_report_patient(target, data["target_identity"])
        if not hasattr(proposal, "patientreconciliationapproval"):
            check_transition(source, target, proposal.link)
            PatientReconciliationApproval.objects.create(proposal=proposal, reviewer=request.user)
            audit(
                request.user, "clinical.reconciliation_approved", proposal.pk, source.organization
            )
        return Response(ReconciliationOutput(proposal).data)
