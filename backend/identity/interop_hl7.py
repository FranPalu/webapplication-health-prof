"""Restricted HL7 v2.5.1 integration engine: validate, identify, quarantine.

No received message creates an encounter, order or signed report automatically.
The durable receipt is idempotent and encrypted; a commit ACK is not clinical review.
"""

import hashlib
import hmac
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from identity.analysis import adult_cutoff, decode_tenant, encode
from identity.clinical import clinical_patients
from identity.clinical_terminology import OBSERVATION_UNITS
from identity.interop_policy import require_enabled
from identity.models import InteropReceipt, Organization
from identity.patient_identification import confirm_report_patient
from identity.security import audit, rate_limit
from identity.services import verified_professional
from identity.views import InputView


class InvalidHL7(ValueError):
    pass


def field(segment, index):
    return segment[index] if index < len(segment) else ""


def parse_message(raw, sending_application, assigning_authority):
    if not sending_application or not assigning_authority:
        raise InvalidHL7("An approved sending application and assigning authority are required.")
    if (
        not isinstance(raw, str)
        or not 0 < len(raw.encode()) <= 65536
        or any(ord(c) < 32 and c != "\r" for c in raw)
    ):
        raise InvalidHL7("Invalid message framing or size.")
    lines = raw.rstrip("\r").split("\r")
    if not 2 <= len(lines) <= 110:
        raise InvalidHL7("Segment limit exceeded.")
    segments = [line.split("|") for line in lines]
    msh = segments[0]
    if (
        field(msh, 0) != "MSH"
        or field(msh, 1) != "^~\\&"
        or field(msh, 2) != sending_application
        or field(msh, 11) != "2.5.1"
    ):
        raise InvalidHL7("Unsupported sender, delimiters or version.")
    message_type = field(msh, 8)
    allowed = {
        "ADT^A01": ("MSH", "PID", "PV1"),
        "ORM^O01": ("MSH", "PID", "ORC", "OBR"),
        "ORU^R01": ("MSH", "PID", "OBR", "OBX"),
    }
    if message_type not in allowed or field(msh, 10) != "T":
        raise InvalidHL7("Only the configured synthetic ADT/ORM/ORU profiles are supported.")
    # Enhanced mode: acknowledge durable commit only. Application review is separate.
    if field(msh, 14) != "AL" or field(msh, 15) != "AL":
        raise InvalidHL7("Enhanced commit/application acknowledgment mode is required.")
    control = field(msh, 9)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", control):
        raise InvalidHL7("Invalid control ID.")
    groups: dict[str, list[list[str]]] = {}
    for segment in segments:
        name = segment[0]
        if name not in allowed[message_type] or name != "OBX" and name in groups:
            raise InvalidHL7(
                "Unsupported or repeated segment; no clinical text is silently discarded."
            )
        groups.setdefault(name, []).append(segment)
    required = set(allowed[message_type])
    if set(groups) != required:
        raise InvalidHL7("Required segments missing.")
    pid = groups["PID"][0]
    identifier = field(pid, 3).split("^")
    if (
        len(identifier) != 5
        or identifier[3] != assigning_authority
        or identifier[4] != "MR"
        or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", identifier[0])
    ):
        raise InvalidHL7("Ambiguous patient identifier or assigning authority.")
    try:
        birth = datetime.strptime(field(pid, 7), "%Y%m%d").date()
    except ValueError as exc:
        raise InvalidHL7("A full patient birth date is required.") from exc
    output = {
        "message_type": message_type,
        "source_confirmation": {
            "identifier_kind": "facility",
            "identifier_value": identifier[0],
            "source_birth_date": birth,
        },
        "proposal": [],
        "status": "quarantined",
        "clinical_review": "DA VALIDARE da professionista abilitato",
    }
    if message_type == "ADT^A01":
        if field(groups["PV1"][0], 2) not in ("I", "O"):
            raise InvalidHL7("Unsupported encounter class.")
        output["proposal"] = [{"resourceType": "Encounter", "status": "planned"}]
    else:
        obr = groups["OBR"][0]
        service = field(obr, 4).split("^")
        if (
            len(service) != 3
            or service[2] != "LN"
            or service[0] not in {"11502-2", *OBSERVATION_UNITS}
        ):
            raise InvalidHL7("Unsupported service code.")
        if message_type == "ORM^O01":
            if field(groups["ORC"][0], 1) != "NW":
                raise InvalidHL7("Corrections/cancellations require supervised reconciliation.")
            output["proposal"] = [
                {
                    "resourceType": "ServiceRequest",
                    "status": "draft",
                    "intent": "order",
                    "code": service[0],
                }
            ]
        else:
            if field(obr, 25) not in ("F", "P"):
                raise InvalidHL7("Unsupported result status; amendments require manual linkage.")
            observations = []
            for obx in groups["OBX"]:
                code, unit = field(obx, 3).split("^"), field(obx, 6).split("^")
                if (
                    field(obx, 2) != "NM"
                    or len(code) != 3
                    or code[2] != "LN"
                    or len(unit) != 3
                    or unit[2] != "UCUM"
                    or OBSERVATION_UNITS.get(code[0]) != unit[0]
                    or field(obx, 11) not in ("F", "P")
                ):
                    raise InvalidHL7("Unsupported numeric observation, code, unit or status.")
                if field(obx, 7) or field(obx, 8):
                    raise InvalidHL7(
                        "Reference limits/flags require a validated sender mapping; no silent loss."
                    )
                number = field(obx, 5)
                if not re.fullmatch(r"[+-]?\d{1,8}(?:\.\d{1,6})?", number):
                    raise InvalidHL7("Uncertain or malformed numeric value.")
                try:
                    value = Decimal(number)
                    if not value.is_finite():
                        raise InvalidOperation
                except InvalidOperation as exc:
                    raise InvalidHL7("Invalid numeric value.") from exc
                observations.append(
                    {
                        "resourceType": "Observation",
                        "status": "preliminary",
                        "code": code[0],
                        "value": str(value),
                        "unit": unit[0],
                    }
                )
            if not 1 <= len(observations) <= 100:
                raise InvalidHL7("Observation limit exceeded.")
            output["proposal"] = observations
    return control, output


class HL7Input(serializers.Serializer):
    message = serializers.CharField(max_length=65536, trim_whitespace=False)


class HL7ReceiptView(InputView):
    serializer_class = HL7Input

    @extend_schema(responses={202: OpenApiTypes.OBJECT})
    def post(self, request, patient_id):
        require_enabled()
        if not verified_professional(request.user):
            raise PermissionDenied()
        rate_limit(request, "hl7-intake", limit=24, by_user=True)
        raw = self.data(request)["message"]
        try:
            control, parsed = parse_message(
                raw, settings.HL7_SENDING_APPLICATION, settings.HL7_ASSIGNING_AUTHORITY
            )
        except InvalidHL7 as exc:
            raise ValidationError(str(exc)) from exc
        with transaction.atomic():
            patient = get_object_or_404(
                clinical_patients(request.user)
                .filter(birth_date__lte=adult_cutoff())
                .select_for_update(of=("self",)),
                pk=patient_id,
            )
            Organization.objects.select_for_update().get(pk=patient.organization_id)
            confirm_report_patient(patient, parsed["source_confirmation"])
            if len(settings.CLINICAL_IDENTITY_KEY) < 32:
                raise PermissionDenied()
            control_hash = hmac.new(
                settings.CLINICAL_IDENTITY_KEY.encode(),
                (settings.HL7_SENDING_APPLICATION + ":" + control).encode(),
                "sha256",
            ).hexdigest()
            previous = InteropReceipt.objects.filter(
                organization=patient.organization, control_digest=control_hash
            ).first()
            # The control-ID namespace belongs to the sender and tenant, not the patient.
            if previous is not None:
                if previous.patient_id != patient.pk:
                    return Response({"code": "control_id_conflict"}, status=409)
                saved = decode_tenant(previous, patient.organization_id)
                if (
                    previous.patient_id != patient.pk
                    or saved["input_sha256"] != hashlib.sha256(raw.encode()).hexdigest()
                ):
                    return Response({"code": "control_id_conflict"}, status=409)
                receipt = previous
            else:
                parsed["source_confirmation"]["source_birth_date"] = parsed["source_confirmation"][
                    "source_birth_date"
                ].isoformat()
                receipt = InteropReceipt.objects.create(
                    organization=patient.organization,
                    patient=patient,
                    author=request.user,
                    control_digest=control_hash,
                    **encode(
                        {
                            "raw_message": raw,
                            "input_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                            "parsed": parsed,
                        },
                        patient.organization_id,
                    ),
                )
            audit(request.user, "interop.hl7_quarantined", receipt.pk, patient.organization)
        timestamp = timezone.now().strftime("%Y%m%d%H%M%S%z")
        ack = f"MSH|^~\\&|CLARIA||{settings.HL7_SENDING_APPLICATION}||{timestamp}||ACK|{receipt.pk}|T|2.5.1\rMSA|CA|{control}\r"
        return Response(
            {
                "id": receipt.pk,
                "state": "quarantined",
                "ack": ack,
                "application_review": "not_performed",
            },
            status=202,
        )


class HL7ReceiptDetailView(InputView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, receipt_id):
        require_enabled()
        if not verified_professional(request.user):
            raise PermissionDenied()
        receipt = get_object_or_404(
            InteropReceipt.objects.select_related("patient__organization"),
            pk=receipt_id,
            patient__in=clinical_patients(request.user),
        )
        audit(request.user, "interop.hl7_read", receipt.pk, receipt.patient.organization)
        return Response(
            {
                "id": receipt.pk,
                "state": "quarantined",
                **decode_tenant(receipt, receipt.organization_id),
            }
        )
