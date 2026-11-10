"""Bounded FHIR R4 gateway reusing the existing clinical access policies."""

import json
import re
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import JSONParser

from identity import clinical, clinical_views, fhir, lab_orders
from identity.analysis import adult_cutoff
from identity.clinical_views import FhirJSONRenderer
from identity.interop_oauth import SmartBearerAuthentication, enforce_scope, fhir_base
from identity.interop_policy import enabled, require_enabled
from identity.models import (
    CareRelationship,
    ClinicalDocumentVersion,
    ClinicalEncounter,
    ClinicalObservation,
    ClinicalReport,
    LabOrder,
    Membership,
    Organization,
    PatientConsent,
    User,
)
from identity.schema import InteropPathSchema
from identity.security import StrictSessionAuthentication, audit, rate_limit
from identity.services import verified_professional, visible_patients
from identity.views import InputView

READERS: dict[str, type[Any]] = {
    "Patient": clinical_views.FhirPatientView,
    "DocumentReference": clinical_views.FhirDocumentView,
    "Organization": fhir.FhirOrganizationView,
    "Practitioner": fhir.FhirPractitionerView,
    "Consent": fhir.FhirConsentView,
    "Encounter": fhir.FhirEncounterView,
    "DiagnosticReport": fhir.FhirReportView,
    "Observation": fhir.FhirObservationView,
    "Provenance": fhir.FhirReportProvenanceView,
    "ServiceRequest": lab_orders.FhirLabOrderView,
}
CONFIRMATION_URL = "urn:claria:fhir:patient-source-confirmation-v1"
CORRECTION_URL = "urn:claria:fhir:correction-reason-v1"


def resource_rows(user, kind):
    if kind == "Patient":
        return visible_patients(user), "pk"
    if kind == "DocumentReference":
        return ClinicalDocumentVersion.objects.filter(
            document__in=clinical.visible_documents(user), purged_at__isnull=True
        ), "document__patient_id"
    if kind == "DiagnosticReport":
        return fhir.visible_reports(user).filter(superseding_revision__isnull=True), "patient_id"
    if kind == "Observation":
        return ClinicalObservation.objects.filter(
            report__in=fhir.visible_reports(user).filter(superseding_revision__isnull=True)
        ), "report__patient_id"
    if kind == "Encounter":
        return ClinicalEncounter.objects.filter(
            patient__in=clinical.clinical_patients(user)
        ), "patient_id"
    if kind == "Consent":
        return PatientConsent.objects.filter(patient__account=user), "patient_id"
    if kind == "Provenance":
        return fhir.visible_reports(user).filter(recorded_at__isnull=False), "patient_id"
    if kind == "ServiceRequest":
        from identity.clinical_safety import require_enabled as safety_enabled

        safety_enabled()
        if not verified_professional(user):
            raise PermissionDenied()
        return LabOrder.objects.filter(patient__in=clinical.clinical_patients(user)), "patient_id"
    if kind == "Organization":
        members = Membership.objects.filter(user=user, active=True).values("organization_id")
        patients = visible_patients(user).values("organization_id")
        return Organization.objects.filter(Q(pk__in=members) | Q(pk__in=patients)), None
    if kind == "Practitioner":
        carers = CareRelationship.objects.filter(
            patient__in=visible_patients(user), active=True
        ).values("professional_id")
        return User.objects.filter(Q(pk__in=carers) | Q(pk=user.pk)).filter(
            is_active=True, role="professional", professionalverification__status="approved"
        ), None
    raise Http404


def read_response(request, kind, resource_id, version=None):
    if kind not in READERS:
        raise Http404
    if kind == "Provenance":
        match = re.fullmatch(r"([0-9a-f-]{36})-v([1-9][0-9]{0,8})", str(resource_id))
        if not match:
            raise Http404
        return READERS[kind]().get(request, resource_id=match[1], version=int(match[2]))
    if kind == "DiagnosticReport":
        return READERS[kind]().get(request, resource_id=resource_id, version=version)
    response = READERS[kind]().get(request, resource_id=resource_id)
    if kind == "DocumentReference" and enabled():
        payload = json.loads(response.content)
        for item in payload.get("content", []):
            attachment = item.get("attachment", {})
            if "url" in attachment:
                attachment["url"] = f"{fhir_base()}/Binary/{payload['id']}"
        return response_json(payload)
    return response


def response_json(payload, status=200, **headers):
    response = JsonResponse(payload, status=status, content_type="application/fhir+json")
    response["Cache-Control"] = "no-store"
    for key, value in headers.items():
        response[key] = value
    return response


def patient_reference(value):
    if not isinstance(value, str):
        raise ValidationError("A local Patient reference is required.")
    try:
        return UUID(value.removeprefix("Patient/"))
    except ValueError as exc:
        raise ValidationError("A local Patient reference is required.") from exc


class FhirJSONParser(JSONParser):
    media_type = "application/fhir+json"


class FhirGatewayView(InputView):
    schema = InteropPathSchema()
    http_method_names = ["get", "head", "options"]
    parser_classes = [FhirJSONParser, JSONParser]
    authentication_classes = [SmartBearerAuthentication, StrictSessionAuthentication]
    renderer_classes = [FhirJSONRenderer]
    serializer_class = fhir.ReportInput
    resource_type = ""

    @extend_schema(responses={(200, "application/fhir+json"): OpenApiTypes.OBJECT})
    def get(self, request, resource_id=None, version=None):
        rate_limit(request, "fhir-read", limit=180, by_user=True)
        kind = self.resource_type
        if kind == "Provenance" and version is not None:
            resource_id = f"{resource_id}-v{version}"
        action = "r" if resource_id is not None else "s"
        enforce_scope(request, kind, action)
        if resource_id is None:
            require_enabled()
            return self.search(request)
        if isinstance(request.auth, dict):
            rows, field = resource_rows(request.user, kind)
            # Token access always intersects both the clinical policy and the grant compartment.
            if field is None:
                raise PermissionDenied()
            if kind == "DiagnosticReport":
                rows = rows.filter(Q(pk=resource_id, root__isnull=True) | Q(root_id=resource_id))
            else:
                rows = rows.filter(pk=resource_id)
            if not rows.filter(**{field: request.auth["grant"].patient_id}).exists():
                raise Http404
        response = read_response(request, kind, resource_id, version)
        response["Cache-Control"] = "no-store"
        if kind == "DiagnosticReport":
            resource = json.loads(response.content)
            response["ETag"] = 'W/"' + resource["meta"]["versionId"] + '"'
        return response

    def search(self, request):
        kind = self.resource_type
        allowed = {"_id", "_count", "_offset"}
        if kind in (
            "DocumentReference",
            "DiagnosticReport",
            "Observation",
            "Encounter",
            "Consent",
            "Provenance",
            "ServiceRequest",
        ):
            allowed.add("patient")
        if kind in ("DiagnosticReport", "Observation", "ServiceRequest"):
            allowed.add("code")
        if set(request.query_params) - allowed or any(
            len(request.query_params.getlist(k)) != 1 for k in request.query_params
        ):
            raise ValidationError("Unsupported or repeated search parameter.")
        try:
            count = int(request.query_params.get("_count", "25"))
            offset = int(request.query_params.get("_offset", "0"))
        except ValueError as exc:
            raise ValidationError("Invalid pagination.") from exc
        if not 1 <= count <= 100 or not 0 <= offset <= 10000:
            raise ValidationError("Pagination limit exceeded.")
        rows, patient_field = resource_rows(request.user, kind)
        patient = request.query_params.get("patient")
        if patient:
            patient_id = patient_reference(patient)
            enforce_scope(request, kind, "s", patient_id)
            rows = rows.filter(**{patient_field: patient_id})
        if isinstance(request.auth, dict):
            rows = rows.filter(**{patient_field: request.auth["grant"].patient_id})
        value = request.query_params.get("_id")
        if value:
            try:
                if kind == "Consent":
                    rows = rows.filter(pk=int(value))
                elif kind == "Provenance":
                    match = re.fullmatch(r"([0-9a-f-]{36})-v([1-9][0-9]{0,8})", value)
                    if not match:
                        raise ValueError
                    rows = rows.filter(
                        Q(pk=UUID(match[1]), root__isnull=True) | Q(root_id=UUID(match[1])),
                        version=int(match[2]),
                    )
                elif kind == "DiagnosticReport":
                    rows = rows.filter(
                        Q(pk=UUID(value), root__isnull=True) | Q(root_id=UUID(value))
                    )
                else:
                    rows = rows.filter(pk=UUID(value))
            except ValueError as exc:
                raise ValidationError("Invalid logical resource ID.") from exc
        code = request.query_params.get("code")
        if code:
            if "|" in code:
                system, code = code.split("|", 1)
                if system != fhir.LOINC_SYSTEM:
                    rows = rows.none()
            rows = rows.filter(code=code)
        total = rows.count()
        entries = []
        for row in rows.order_by("pk")[offset : offset + count]:
            logical_id = str(row.pk)
            if kind in ("DiagnosticReport", "Provenance"):
                logical_id = str(row.root_id or row.pk)
                if kind == "Provenance":
                    logical_id += f"-v{row.version}"
            resource = json.loads(read_response(request, kind, logical_id).content)
            entries.append(
                {
                    "fullUrl": f"{fhir_base()}/{kind}/{logical_id}",
                    "resource": resource,
                    "search": {"mode": "match"},
                }
            )
        parameters = dict(request.query_params.items())
        parameters.update(_count=str(count), _offset=str(offset))
        links = [{"relation": "self", "url": f"{fhir_base()}/{kind}?{urlencode(parameters)}"}]
        if offset + count < total:
            parameters["_offset"] = str(offset + count)
            links.append(
                {"relation": "next", "url": f"{fhir_base()}/{kind}?{urlencode(parameters)}"}
            )
        audit(request.user, "interop.fhir_searched", kind)
        return response_json(
            {
                "resourceType": "Bundle",
                "type": "searchset",
                "total": total,
                "link": links,
                "entry": entries,
            }
        )

    @extend_schema(
        request=OpenApiTypes.OBJECT, responses={(201, "application/fhir+json"): OpenApiTypes.OBJECT}
    )
    def post(self, request):
        return self.write(request)

    @extend_schema(
        request=OpenApiTypes.OBJECT, responses={(200, "application/fhir+json"): OpenApiTypes.OBJECT}
    )
    def put(self, request, resource_id):
        return self.write(request, resource_id)

    def write(self, request, resource_id=None):
        require_enabled()
        enforce_scope(request, self.resource_type, "u" if resource_id else "c")
        if self.resource_type != "DiagnosticReport" or not verified_professional(request.user):
            raise PermissionDenied("Only supervised preliminary report intake is writable.")
        if request.headers.get("If-None-Exist"):
            raise ValidationError("Conditional create is not supported.")
        rate_limit(request, "fhir-write", limit=24, by_user=True)
        if "id" in request.data and (resource_id is None or request.data["id"] != str(resource_id)):
            raise ValidationError("Logical ID does not match the interaction.")
        data, patient_id = report_input(request.data, correction=resource_id is not None)
        with transaction.atomic():
            patient = get_object_or_404(
                clinical.clinical_patients(request.user)
                .filter(birth_date__lte=adult_cutoff())
                .select_for_update(of=("self",)),
                pk=patient_id,
            )
            root = previous = None
            if resource_id is not None:
                root = get_object_or_404(
                    ClinicalReport.objects.select_for_update(),
                    pk=resource_id,
                    root__isnull=True,
                    patient=patient,
                    author=request.user,
                )
                previous = root.revisions.order_by("-version").first() or root
                if request.headers.get("If-Match") != f'W/"{previous.version}"':
                    return response_json(
                        {
                            "resourceType": "OperationOutcome",
                            "issue": [{"severity": "error", "code": "conflict"}],
                        },
                        status=412,
                    )
            serializer: fhir.ReportInput
            if previous is not None:
                data["expected_version"] = previous.version
                serializer = fhir.ReportCorrectionInput(data=data)
            else:
                serializer = fhir.ReportInput(data=data)
            serializer.is_valid(raise_exception=True)
            response = fhir.store_report(
                request, patient, serializer.validated_data, root=root, previous=previous
            )
            logical_id = response.data["id"]
            number = response.data["version"]
            payload = json.loads(
                read_response(request, "DiagnosticReport", logical_id, number).content
            )
            return response_json(
                payload,
                status=200 if resource_id else 201,
                ETag=f'W/"{number}"',
                Location=f"{fhir_base()}/DiagnosticReport/{logical_id}/_history/{number}",
            )


def exact_keys(data, allowed):
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValidationError("Unsupported fields in the restricted FHIR intake profile.")


def single_coding(data):
    exact_keys(data, {"coding", "text"})
    codings = data.get("coding")
    if not isinstance(codings, list) or len(codings) != 1:
        raise ValidationError("One supported LOINC coding is required.")
    exact_keys(codings[0], {"system", "code", "display"})
    if codings[0].get("system") != fhir.LOINC_SYSTEM:
        raise ValidationError("Unsupported terminology system.")
    return codings[0]


def report_input(payload, *, correction=False):
    exact_keys(
        payload,
        {
            "resourceType",
            "id",
            "status",
            "code",
            "subject",
            "effectiveDateTime",
            "contained",
            "result",
            "extension",
        },
    )
    if payload.get("resourceType") != "DiagnosticReport" or payload.get("status") != "preliminary":
        raise ValidationError("Unsigned imports must be preliminary DiagnosticReport resources.")
    exact_keys(payload.get("subject"), {"reference"})
    patient_id = patient_reference(payload["subject"].get("reference"))
    coding = single_coding(payload.get("code"))
    data = {
        "code": coding.get("code"),
        "title": coding.get("display") or payload["code"].get("text"),
        "effective_at": payload.get("effectiveDateTime"),
    }
    extensions = payload.get("extension", [])
    if not isinstance(extensions, list) or len(extensions) != (2 if correction else 1):
        raise ValidationError(
            "Independent patient confirmation and correction reason are required."
        )
    for extension in extensions:
        exact_keys(extension, {"url", "extension", "valueString"})
        if extension.get("url") == CONFIRMATION_URL:
            values = extension.get("extension")
            if not isinstance(values, list) or len(values) != 3:
                raise ValidationError("Invalid source confirmation.")
            for item in values:
                exact_keys(item, {"url", "valueString"})
                if (
                    item.get("url")
                    not in ("identifier_kind", "identifier_value", "source_birth_date")
                    or item["url"] in data
                ):
                    raise ValidationError("Invalid source confirmation.")
                data[item["url"]] = item.get("valueString")
        elif (
            correction
            and extension.get("url") == CORRECTION_URL
            and "correction_reason" not in data
        ):
            data["correction_reason"] = extension.get("valueString")
        else:
            raise ValidationError("Unknown or repeated intake extension.")
    if correction and not data.get("correction_reason"):
        raise ValidationError("A correction reason is required.")
    contained, refs = payload.get("contained"), payload.get("result")
    if (
        not isinstance(contained, list)
        or not 1 <= len(contained) <= 100
        or not isinstance(refs, list)
        or len(refs) != len(contained)
    ):
        raise ValidationError("A bounded set of contained observations is required.")
    observations, ids = [], set()
    for item in contained:
        exact_keys(item, {"resourceType", "id", "status", "code", "valueQuantity"})
        identifier = item.get("id")
        if (
            item.get("resourceType") != "Observation"
            or item.get("status") != "preliminary"
            or not isinstance(identifier, str)
            or not re.fullmatch(r"[A-Za-z0-9.-]{1,64}", identifier)
            or identifier in ids
        ):
            raise ValidationError("Invalid contained observation.")
        ids.add(identifier)
        code = single_coding(item.get("code"))
        value = item.get("valueQuantity")
        exact_keys(value, {"value", "unit", "system", "code"})
        if value.get("system") != fhir.UCUM_SYSTEM or value.get("unit") not in (
            None,
            value.get("code"),
        ):
            raise ValidationError("UCUM unit mismatch.")
        observations.append(
            {
                "code": code.get("code"),
                "display": code.get("display") or item["code"].get("text"),
                "value": value.get("value"),
                "unit": value.get("code"),
            }
        )
    expected = set()
    for ref in refs:
        exact_keys(ref, {"reference"})
        if not isinstance(ref.get("reference"), str):
            raise ValidationError("Invalid contained reference.")
        expected.add(ref["reference"])
    if expected != {"#" + identifier for identifier in ids}:
        raise ValidationError("Contained references do not match the observations.")
    data["observations"] = observations
    return data, patient_id


class FhirCapabilityView(clinical_views.FhirMetadataView):
    authentication_classes = [SmartBearerAuthentication, StrictSessionAuthentication]

    @extend_schema(responses={(200, "application/fhir+json"): OpenApiTypes.OBJECT})
    def get(self, request):
        response = super().get(request)
        payload = json.loads(response.content)
        payload["date"] = "2026-11-09"
        if enabled():
            for resource in payload["rest"][0]["resource"]:
                kind = resource["type"]
                resource["interaction"].append({"code": "search-type"})
                parameters = [{"name": "_id", "type": "token"}]
                if kind not in ("Patient", "Organization", "Practitioner"):
                    parameters.append({"name": "patient", "type": "reference"})
                if kind in ("DiagnosticReport", "Observation", "ServiceRequest"):
                    parameters.append({"name": "code", "type": "token"})
                resource["searchParam"] = parameters
                if kind == "DiagnosticReport":
                    resource["interaction"] += [{"code": "create"}, {"code": "update"}]
                    resource["versioning"] = "versioned-update"
                    resource["updateCreate"] = False
                    resource["conditionalCreate"] = False
                    resource["documentation"] = (
                        "Restricted preliminary lab intake with independent patient confirmation; no final signature or generic FHIR writes."
                    )
            payload["rest"][0]["resource"].append(
                {
                    "type": "Binary",
                    "interaction": [{"code": "read"}],
                    "documentation": "Read allowed only through the authorized DocumentReference security context; no unconstrained Binary scope.",
                }
            )
            payload["rest"][0]["security"] = {
                "cors": False,
                "description": "Session access and optional delegated SMART patient read/search scopes. No authorization server is bundled.",
            }
        audit(request.user, "interop.fhir_capabilities_read")
        return response_json(payload)


class FhirReportCollectionView(FhirGatewayView):
    http_method_names = ["get", "post", "head", "options"]
    resource_type = "DiagnosticReport"


class FhirReportInstanceView(FhirGatewayView):
    http_method_names = ["get", "put", "head", "options"]
    resource_type = "DiagnosticReport"


class FhirBinaryView(InputView):
    authentication_classes = [SmartBearerAuthentication, StrictSessionAuthentication]
    renderer_classes = [FhirJSONRenderer]
    schema = InteropPathSchema()

    @extend_schema(responses={(200, "application/fhir+json"): OpenApiTypes.OBJECT})
    def get(self, request, resource_id):
        import base64

        from identity.clinical_storage import read_content

        require_enabled()
        enforce_scope(request, "DocumentReference", "r")
        version = get_object_or_404(
            ClinicalDocumentVersion.objects.select_related("document__patient__organization"),
            pk=resource_id,
            document__in=clinical.visible_documents(request.user, "download"),
            purged_at__isnull=True,
        )
        enforce_scope(request, "DocumentReference", "r", version.document.patient_id)
        content = read_content(version)
        audit(
            request.user,
            "interop.fhir_binary_read",
            version.pk,
            version.document.patient.organization,
        )
        return response_json(
            {
                "resourceType": "Binary",
                "id": str(version.pk),
                "contentType": version.media_type,
                "securityContext": {"reference": f"DocumentReference/{version.pk}"},
                "data": base64.b64encode(content).decode(),
            }
        )
