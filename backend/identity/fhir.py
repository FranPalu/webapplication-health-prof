from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from identity.clinical import clinical_patients, shared_scopes
from identity.clinical_views import FhirJSONRenderer
from identity.models import (
    CareRelationship,
    ClinicalObservation,
    ClinicalReport,
    Membership,
    Organization,
    Patient,
    PatientConsent,
    User,
)
from identity.security import audit
from identity.services import verified_professional, visible_patients
from identity.views import InputView


def concept(code, label):
    return {"coding": [{"system": "http://loinc.org", "code": code}], "text": label}


class ObservationInput(serializers.Serializer):
    code = serializers.RegexField(r"^[0-9]{1,12}-[0-9]$")
    display = serializers.CharField(source="label", max_length=160)
    value = serializers.DecimalField(max_digits=16, decimal_places=6)
    unit = serializers.CharField(max_length=32)


class ReportInput(serializers.Serializer):
    code = serializers.RegexField(r"^[0-9]{1,12}-[0-9]$")
    title = serializers.CharField(max_length=160)
    effective_at = serializers.DateTimeField()
    observations = ObservationInput(many=True, allow_empty=False)

    def validate_observations(self, value):
        if len(value) > 100:
            raise serializers.ValidationError("At most 100 observations are allowed.")
        return value


class ReportCreateView(InputView):
    serializer_class = ReportInput

    @transaction.atomic
    @extend_schema(responses={201: OpenApiTypes.OBJECT})
    def post(self, request, patient_id):
        if not verified_professional(request.user):
            raise PermissionDenied()
        patient = get_object_or_404(clinical_patients(request.user), pk=patient_id)
        data = self.data(request)
        observations = data.pop("observations")
        report = ClinicalReport.objects.create(patient=patient, author=request.user, **data)
        ClinicalObservation.objects.bulk_create(
            ClinicalObservation(report=report, **observation) for observation in observations
        )
        audit(request.user, "clinical.report_created", report.pk, patient.organization)
        return Response({"id": str(report.pk)}, status=201)


class FhirReadView(InputView):
    renderer_classes = [FhirJSONRenderer]
    serializer_class = ReportInput
    resource_type = ""

    @extend_schema(responses={(200, "application/fhir+json"): OpenApiTypes.OBJECT})
    def get(self, request, resource_id):
        fields, organization = self.read(request.user, resource_id)
        audit(request.user, "clinical.fhir_read", resource_id, organization)
        return JsonResponse(
            {"resourceType": self.resource_type, "id": str(resource_id), **fields},
            content_type="application/fhir+json",
        )

    def read(self, user, resource_id):
        raise NotImplementedError


class FhirOrganizationView(FhirReadView):
    resource_type = "Organization"

    def read(self, user, resource_id):
        members = Membership.objects.filter(user=user, active=True).values("organization_id")
        patients = visible_patients(user).values("organization_id")
        organization = get_object_or_404(
            Organization.objects.filter(pk__in=members.union(patients)), pk=resource_id
        )
        return {"name": organization.name, "active": True}, organization


class FhirPractitionerView(FhirReadView):
    resource_type = "Practitioner"

    def read(self, user, resource_id):
        visible = CareRelationship.objects.filter(
            patient__in=visible_patients(user), active=True
        ).values("professional_id")
        practitioner = get_object_or_404(
            User.objects.filter(pk__in=visible) | User.objects.filter(pk=user.pk),
            pk=resource_id,
            is_active=True,
        )
        if not verified_professional(practitioner):
            from django.http import Http404

            raise Http404
        name: dict[str, str | list[str]] = {}
        if practitioner.first_name:
            name["given"] = [practitioner.first_name]
        if practitioner.last_name:
            name["family"] = practitioner.last_name
        return {"active": True, **({"name": [name]} if name else {})}, None


class FhirConsentView(FhirReadView):
    resource_type = "Consent"

    def read(self, user, resource_id):
        consent = get_object_or_404(
            PatientConsent.objects.select_related("patient__organization", "text_version"),
            pk=resource_id,
            patient__account=user,
        )
        latest = (
            PatientConsent.objects.filter(
                patient=consent.patient,
                share=consent.share,
                text_version__purpose=consent.text_version.purpose,
            )
            .order_by("-created_at", "-pk")
            .first()
        )
        from identity.services import share_is_active

        active = consent == latest and consent.decision == "granted"
        if consent.share_id:
            active = active and share_is_active(consent.share)
        return {
            "status": "active" if active else "inactive",
            "scope": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/consentscope",
                        "code": "patient-privacy",
                    }
                ]
            },
            "category": [{"text": consent.text_version.purpose}],
            "patient": {"reference": f"Patient/{consent.patient_id}"},
            "dateTime": consent.created_at.isoformat(),
            "provision": {"type": "permit" if consent.decision == "granted" else "deny"},
        }, consent.patient.organization


def report_patients(user):
    charts, _, _ = shared_scopes(user, "view")
    return Patient.objects.filter(Q(pk__in=visible_patients(user)) | Q(pk__in=charts))


def subject(user, patient_id):
    if visible_patients(user).filter(pk=patient_id).exists():
        return {"subject": {"reference": f"Patient/{patient_id}"}}
    return {}


class FhirReportView(FhirReadView):
    resource_type = "DiagnosticReport"

    def read(self, user, resource_id):
        report = get_object_or_404(
            ClinicalReport.objects.select_related("patient__organization"),
            patient__in=report_patients(user),
            pk=resource_id,
        )
        return {
            "status": "final",
            "code": concept(report.code, report.title),
            **subject(user, report.patient_id),
            "effectiveDateTime": report.effective_at.isoformat(),
            "result": [
                {"reference": f"Observation/{observation_id}"}
                for observation_id in report.observations.values_list("id", flat=True)
            ],
        }, report.patient.organization


class FhirObservationView(FhirReadView):
    resource_type = "Observation"

    def read(self, user, resource_id):
        observation = get_object_or_404(
            ClinicalObservation.objects.select_related("report__patient__organization"),
            report__patient__in=report_patients(user),
            pk=resource_id,
        )
        report = observation.report
        return {
            "status": "final",
            "code": concept(observation.code, observation.label),
            **subject(user, report.patient_id),
            "effectiveDateTime": report.effective_at.isoformat(),
            "valueQuantity": {"value": float(observation.value), "unit": observation.unit},
        }, report.patient.organization
