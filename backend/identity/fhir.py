from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from identity.clinical import clinical_patients, shared_scopes
from identity.clinical_terminology import (
    LOINC_SYSTEM,
    OBSERVATION_UNITS,
    PROFILE_VERSION,
    REPORT_CODES,
    UCUM_SYSTEM,
)
from identity.clinical_views import FhirJSONRenderer
from identity.models import (
    CareRelationship,
    ClinicalEncounter,
    ClinicalObservation,
    ClinicalReport,
    Membership,
    Organization,
    Patient,
    PatientConsent,
    User,
)
from identity.patient_identification import IdentifierInput, confirm_report_patient
from identity.security import audit, rate_limit
from identity.services import verified_professional, visible_patients
from identity.views import InputView


def concept(code, label):
    return {"coding": [{"system": LOINC_SYSTEM, "code": code}], "text": label}


class ReferenceRangeInput(serializers.Serializer):
    low = serializers.DecimalField(max_digits=14, decimal_places=6, required=False)
    high = serializers.DecimalField(max_digits=14, decimal_places=6, required=False)
    laboratory = serializers.CharField(max_length=120)
    min_age_years = serializers.IntegerField(min_value=0, max_value=130, required=False)
    max_age_years = serializers.IntegerField(min_value=0, max_value=130, required=False)
    sex = serializers.ChoiceField(choices=["female", "male"], required=False)

    def validate(self, data):
        low, high = data.get("low"), data.get("high")
        if low is None and high is None or low is not None and high is not None and low > high:
            raise ValidationError("Invalid reported reference limits.")
        if data.get("min_age_years", 0) > data.get("max_age_years", 130):
            raise ValidationError("Invalid reported reference age limits.")
        return {key: str(value) if key in ("low", "high") else value for key, value in data.items()}


class ObservationInput(serializers.Serializer):
    code = serializers.ChoiceField(choices=sorted(OBSERVATION_UNITS))
    display = serializers.CharField(source="label", max_length=160)
    value = serializers.DecimalField(max_digits=14, decimal_places=6)
    unit = serializers.CharField(max_length=32, trim_whitespace=False)
    reference_range = ReferenceRangeInput(required=False)

    def validate(self, data):
        if data["unit"] != OBSERVATION_UNITS[data["code"]]:
            raise ValidationError(
                {"unit": "Use the UCUM code supported for this LOINC observation."}
            )
        return data


class ReportInput(IdentifierInput):
    code = serializers.ChoiceField(choices=sorted(REPORT_CODES))
    title = serializers.CharField(max_length=160)
    effective_at = serializers.DateTimeField()
    encounter_id = serializers.UUIDField(required=False)
    observations = ObservationInput(many=True, allow_empty=False)

    def validate_effective_at(self, value):
        if value > timezone.now():
            raise ValidationError("The source report date cannot be in the future.")
        return value

    def validate_observations(self, value):
        if len(value) > 100:
            raise ValidationError("At most 100 observations are allowed.")
        return value


class ReportCorrectionInput(ReportInput):
    expected_version = serializers.IntegerField(min_value=1)
    correction_reason = serializers.CharField(max_length=500)


class ReportOutput(serializers.Serializer):
    id = serializers.UUIDField()
    version = serializers.IntegerField()


def store_report(request, patient, data, *, root=None, previous=None):
    confirm_report_patient(patient, data)
    encounter_id = data.get("encounter_id")
    if (
        encounter_id is not None
        and not ClinicalEncounter.objects.filter(pk=encounter_id, patient=patient).exists()
    ):
        raise ValidationError({"encounter_id": "Encounter does not belong to the patient."})
    report = ClinicalReport.objects.create(
        patient=patient,
        author=request.user,
        code=data["code"],
        encounter_id=encounter_id,
        title=data["title"],
        effective_at=data["effective_at"],
        recorded_at=timezone.now(),
        root=root,
        previous=previous,
        version=previous.version + 1 if previous else 1,
        correction_reason=data.get("correction_reason", ""),
        terminology_version=PROFILE_VERSION,
    )
    ClinicalObservation.objects.bulk_create(
        ClinicalObservation(report=report, **observation) for observation in data["observations"]
    )
    audit(
        request.user,
        "clinical.report_corrected" if previous else "clinical.report_created",
        report.pk,
        patient.organization,
    )
    return Response({"id": root.pk if root else report.pk, "version": report.version}, status=201)


class EncounterInput(IdentifierInput):
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField()

    def validate(self, data):
        if not data["started_at"] <= data["ended_at"] <= timezone.now():
            raise ValidationError("A completed encounter with an ordered period is required.")
        return data


class EncounterOutput(serializers.Serializer):
    id = serializers.UUIDField()


class EncounterCreateView(InputView):
    serializer_class = EncounterInput

    @extend_schema(responses={201: EncounterOutput})
    def post(self, request, patient_id):
        if not verified_professional(request.user):
            raise PermissionDenied()
        rate_limit(request, "clinical-encounter-write", limit=24, by_user=True)
        data = self.data(request)
        with transaction.atomic():
            patient = get_object_or_404(
                clinical_patients(request.user).select_for_update(of=("self",)), pk=patient_id
            )
            confirm_report_patient(patient, data)
            encounter = ClinicalEncounter.objects.create(
                patient=patient,
                author=request.user,
                started_at=data["started_at"],
                ended_at=data["ended_at"],
            )
            audit(request.user, "clinical.encounter_created", encounter.pk, patient.organization)
        return Response({"id": encounter.pk}, status=201)


class ReportCreateView(InputView):
    serializer_class = ReportInput

    @extend_schema(responses={201: ReportOutput})
    def post(self, request, patient_id):
        if not verified_professional(request.user):
            raise PermissionDenied()
        rate_limit(request, "clinical-report-write", limit=24, by_user=True)
        data = self.data(request)
        with transaction.atomic():
            patient = get_object_or_404(
                clinical_patients(request.user).select_for_update(of=("self",)), pk=patient_id
            )
            return store_report(request, patient, data)


class ReportCorrectionView(InputView):
    serializer_class = ReportCorrectionInput

    @extend_schema(responses={201: ReportOutput})
    def post(self, request, report_id):
        if not verified_professional(request.user):
            raise PermissionDenied()
        rate_limit(request, "clinical-report-write", limit=24, by_user=True)
        data = self.data(request)
        with transaction.atomic():
            root = get_object_or_404(
                ClinicalReport.objects.select_for_update(of=("self",)).select_related("patient"),
                pk=report_id,
                root__isnull=True,
                author=request.user,
                patient__in=clinical_patients(request.user),
            )
            previous = root.revisions.order_by("-version").first() or root
            if previous.version != data["expected_version"]:
                return Response({"code": "report_version_conflict"}, status=409)
            return store_report(request, root.patient, data, root=root, previous=previous)


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


class FhirEncounterView(FhirReadView):
    resource_type = "Encounter"

    def read(self, user, resource_id):
        encounter = get_object_or_404(
            ClinicalEncounter.objects.select_related("patient__organization"),
            patient__in=clinical_patients(user),
            pk=resource_id,
        )
        return {
            "status": "finished",
            "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"},
            "subject": {"reference": f"Patient/{encounter.patient_id}"},
            "period": {
                "start": encounter.started_at.isoformat(),
                "end": encounter.ended_at.isoformat(),
            },
        }, encounter.patient.organization


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


def visible_reports(user):
    return ClinicalReport.objects.filter(patient__in=report_patients(user)).filter(
        Q(recorded_at__isnull=True) | Q(patient__in=clinical_patients(user))
    )


def report_status(report):
    return "preliminary" if report.recorded_at else "unknown"


def report_payload(user, report):
    meta = {"versionId": str(report.version)}
    if report.recorded_at:
        meta["lastUpdated"] = report.recorded_at.isoformat()
    encounter = (
        {"encounter": {"reference": f"Encounter/{report.encounter_id}"}}
        if report.encounter_id
        else {}
    )
    return {
        "resourceType": "DiagnosticReport",
        "id": str(report.root_id or report.pk),
        "meta": meta,
        "status": report_status(report),
        "code": concept(report.code, report.title),
        **subject(user, report.patient_id),
        **encounter,
        "effectiveDateTime": report.effective_at.isoformat(),
        "result": [
            {"reference": f"Observation/{observation_id}"}
            for observation_id in report.observations.order_by("pk").values_list("id", flat=True)
        ],
    }


class FhirReportView(FhirReadView):
    @extend_schema(responses={(200, "application/fhir+json"): OpenApiTypes.OBJECT})
    def get(self, request, resource_id, version=None):
        rows = visible_reports(request.user).filter(Q(pk=resource_id) | Q(root_id=resource_id))
        # Only the logical root ID is a public DiagnosticReport ID.
        rows = rows.filter(Q(root_id=resource_id) | Q(root__isnull=True))
        as_of = request.query_params.get("as_of")
        if as_of is not None:
            try:
                at = parse_datetime(as_of)
            except ValueError:
                at = None
            if at is None or timezone.is_naive(at) or version is not None:
                raise ValidationError("Use an ISO-8601 date-time with offset for as_of.")
            rows = rows.filter(recorded_at__lte=at)
        if version is not None:
            rows = rows.filter(version=version)
        report = rows.select_related("patient__organization").order_by("-version").first()
        if report is None:
            raise Http404
        audit(request.user, "clinical.fhir_read", report.pk, report.patient.organization)
        return JsonResponse(
            report_payload(request.user, report), content_type="application/fhir+json"
        )


def quantity(value, unit):
    return {"value": float(value), "unit": unit, "system": UCUM_SYSTEM, "code": unit}


def reference_range(data, unit):
    bounds = {key: quantity(data[key], unit) for key in ("low", "high") if key in data}
    ages = {
        key: quantity(data[field], "a")
        for key, field in (("low", "min_age_years"), ("high", "max_age_years"))
        if field in data
    }
    label = "Laboratory: " + data["laboratory"]
    if "sex" in data:
        label += ". Reported sex context: " + data["sex"]
    return {**bounds, "text": label, **({"age": ages} if ages else {})}


class FhirReportProvenanceView(InputView):
    renderer_classes = [FhirJSONRenderer]
    serializer_class = ReportOutput

    @extend_schema(responses={(200, "application/fhir+json"): OpenApiTypes.OBJECT})
    def get(self, request, resource_id, version):
        report = get_object_or_404(
            visible_reports(request.user)
            .filter(Q(root_id=resource_id) | Q(pk=resource_id, root__isnull=True))
            .select_related("patient__organization"),
            version=version,
            recorded_at__isnull=False,
        )
        audit(request.user, "clinical.fhir_read", report.pk, report.patient.organization)
        return JsonResponse(
            {
                "resourceType": "Provenance",
                "id": f"{resource_id}-v{version}",
                "target": [{"reference": f"DiagnosticReport/{resource_id}/_history/{version}"}],
                "recorded": report.recorded_at.isoformat(),
                "agent": [{"who": {"reference": f"Practitioner/{report.author_id}"}}],
            },
            content_type="application/fhir+json",
        )


class FhirObservationView(FhirReadView):
    resource_type = "Observation"

    def read(self, user, resource_id):
        observation = get_object_or_404(
            ClinicalObservation.objects.select_related("report__patient__organization"),
            report__in=visible_reports(user),
            pk=resource_id,
        )
        report = observation.report
        value = (
            quantity(observation.value, observation.unit)
            if report.terminology_version
            else {"value": float(observation.value), "unit": observation.unit}
        )
        ranges = (
            {"referenceRange": [reference_range(observation.reference_range, observation.unit)]}
            if observation.reference_range
            else {}
        )
        return {
            "status": report_status(report),
            "code": concept(observation.code, observation.label),
            **subject(user, report.patient_id),
            "effectiveDateTime": report.effective_at.isoformat(),
            "valueQuantity": value,
            **ranges,
        }, report.patient.organization
