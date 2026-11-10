"""Synthetic single-frame CR/DX/SC PACS bridge with pseudonymized derivatives.

Tag removal is not proof of anonymity, and pixel labels are not detected. Input
must explicitly declare BurnedInAnnotation=NO; clinical deployment is blocked.
"""

import base64
import copy
import hashlib
import hmac
import json
import re
import ssl
from datetime import datetime
from io import BytesIO
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPSHandler, Request, build_opener

from django.conf import settings
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiTypes, extend_schema
from pydicom import dcmread, dcmwrite
from pydicom.datadict import dictionary_VR
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.errors import InvalidDicomError
from pydicom.uid import ExplicitVRLittleEndian, ImplicitVRLittleEndian
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from identity.analysis import adult_cutoff
from identity.clinical import clinical_patients, visible_documents
from identity.clinical_storage import read_content
from identity.interop_oauth import IntegrationUnavailable, NoRedirects
from identity.interop_policy import require_enabled
from identity.models import ClinicalDocumentVersion, PacsStudyLink
from identity.patient_identification import IdentifierInput, confirm_report_patient
from identity.schema import InteropPathSchema
from identity.security import audit, rate_limit
from identity.services import verified_professional
from identity.views import InputView

UID = r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))+"
SOP_CLASSES = frozenset(
    {"1.2.840.10008.5.1.4.1.1.1", "1.2.840.10008.5.1.4.1.1.1.1", "1.2.840.10008.5.1.4.1.1.7"}
)
SAFE_TAGS = (
    "SOPClassUID",
    "Modality",
    "Rows",
    "Columns",
    "SamplesPerPixel",
    "PhotometricInterpretation",
    "BitsAllocated",
    "BitsStored",
    "HighBit",
    "PixelRepresentation",
    "PixelData",
    "PixelSpacing",
    "ImagerPixelSpacing",
    "ImageOrientationPatient",
    "ImagePositionPatient",
    "RescaleIntercept",
    "RescaleSlope",
    "WindowCenter",
    "WindowWidth",
    "PresentationLUTShape",
    "InstanceNumber",
    "SeriesNumber",
)


def pseudonym_uid(value, namespace):
    if not isinstance(value, str) or len(value) > 64 or not re.fullmatch(UID, value):
        raise ValueError("Invalid source UID.")
    number = int.from_bytes(hmac.digest(namespace, value.encode(), "sha256")[:16], "big")
    return "2.25." + str(number)


def deidentify(data, namespace):
    if not 0 < len(data) <= 10 * 1024 * 1024 or len(namespace) < 32:
        raise ValueError("Input or namespace limit.")
    source = dcmread(BytesIO(data), force=False)
    transfer = str(source.file_meta.TransferSyntaxUID)
    if (
        str(source.SOPClassUID) not in SOP_CLASSES
        or str(source.Modality) not in ("CR", "DX", "OT")
        or transfer not in (str(ExplicitVRLittleEndian), str(ImplicitVRLittleEndian))
        or getattr(source, "BurnedInAnnotation", "") != "NO"
        or int(getattr(source, "NumberOfFrames", 1)) != 1
        or int(source.SamplesPerPixel) != 1
        or source.PhotometricInterpretation not in ("MONOCHROME1", "MONOCHROME2")
        or not 1 <= int(source.Rows) <= 4096
        or not 1 <= int(source.Columns) <= 4096
        or int(source.BitsAllocated) not in (8, 16)
        or int(source.PixelRepresentation) not in (0, 1)
        or not 1 <= int(source.BitsStored) <= int(source.BitsAllocated)
        or int(source.HighBit) != int(source.BitsStored) - 1
    ):
        raise ValueError("Unsupported image or insufficient privacy/geometry declaration.")
    size = int(source.Rows) * int(source.Columns) * int(source.BitsAllocated) // 8
    if len(source.PixelData) not in (size, size + (size % 2)):
        raise ValueError("Pixel data length mismatch.")
    target = Dataset()
    for name in SAFE_TAGS:
        if name in source:
            element = source.data_element(name)
            if element is not None:
                if element.VR == "SQ" or element.VR not in dictionary_VR(element.tag).split(" or "):
                    raise ValueError("Unexpected representation in the allowed scalar tags")
                target.add(copy.deepcopy(element))
    for name in ("StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID"):
        setattr(target, name, pseudonym_uid(str(getattr(source, name)), namespace))
    target.PatientID = hmac.digest(namespace, b"patient-pacs", "sha256").hex()
    target.PatientName = ""
    target.PatientBirthDate = ""
    target.PatientSex = ""
    target.StudyDate = ""
    target.StudyTime = ""
    target.AccessionNumber = ""
    target.StudyID = ""
    target.PatientIdentityRemoved = "YES"
    target.BurnedInAnnotation = "NO"
    target.DeidentificationMethod = "Claria synthetic allow-list v1; pixel privacy not validated"
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = source.file_meta.TransferSyntaxUID
    meta.MediaStorageSOPClassUID = target.SOPClassUID
    meta.MediaStorageSOPInstanceUID = target.SOPInstanceUID
    target.file_meta = meta
    output = BytesIO()
    dcmwrite(output, target, enforce_file_format=True)
    return (
        output.getvalue(),
        str(target.StudyInstanceUID),
        str(target.SeriesInstanceUID),
        str(target.SOPInstanceUID),
    )


def pacs_request(method, path, *, body=None, accept="application/dicom+json", content_type=None):
    base = settings.PACS_DICOMWEB_URL.rstrip("/")
    parsed = urlsplit(base)
    local = (
        settings.DEBUG
        and parsed.scheme == "http"
        and parsed.hostname == "orthanc"
        and parsed.port == 8042
    )
    if (
        (not local and parsed.scheme != "https")
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.hostname
        or not settings.PACS_USERNAME
        or not settings.PACS_PASSWORD
    ):
        raise IntegrationUnavailable()
    headers = {
        "Accept": accept,
        "Authorization": "Basic "
        + base64.b64encode(
            (settings.PACS_USERNAME + ":" + settings.PACS_PASSWORD).encode()
        ).decode(),
    }
    if content_type:
        headers["Content-Type"] = content_type
    request = Request(base + path, data=body, headers=headers, method=method)
    try:
        opener = build_opener(NoRedirects(), HTTPSHandler(context=ssl.create_default_context()))
        with opener.open(request, timeout=10) as response:
            result = response.read(32 * 1024 * 1024 + 1)
            media_type = response.headers.get("Content-Type", "")
        if len(result) > 32 * 1024 * 1024:
            raise ValueError("PACS response limit")
        return result, media_type
    except (OSError, ValueError) as exc:
        raise IntegrationUnavailable() from exc


class PacsInput(IdentifierInput):
    version = serializers.UUIDField()


class PacsImportView(InputView):
    serializer_class = PacsInput

    @extend_schema(responses={201: OpenApiTypes.OBJECT})
    def post(self, request, patient_id):
        require_enabled()
        if not verified_professional(request.user):
            raise PermissionDenied()
        rate_limit(request, "pacs-store", limit=12, by_user=True)
        data = self.data(request)
        with transaction.atomic():
            patient = get_object_or_404(
                clinical_patients(request.user)
                .filter(birth_date__lte=adult_cutoff())
                .select_for_update(of=("self",)),
                pk=patient_id,
            )
            confirm_report_patient(patient, data)
            version = get_object_or_404(
                ClinicalDocumentVersion,
                pk=data["version"],
                document__patient=patient,
                document__in=visible_documents(request.user, "download"),
                media_type="application/dicom",
                purged_at__isnull=True,
            )
            existing = PacsStudyLink.objects.filter(version=version).first()
            if existing:
                return Response({"study_uid": existing.study_uid}, status=201)
            namespace = hmac.digest(
                settings.CLINICAL_IDENTITY_KEY.encode(),
                f"pacs:{patient.organization_id}:{patient.pk}".encode(),
                "sha256",
            )
            content = read_content(version)
            if (
                hashlib.sha256(content).hexdigest() != version.sha256
                or len(settings.CLINICAL_IDENTITY_KEY) < 32
            ):
                raise ValidationError("Source identity unavailable.")
            try:
                source = dcmread(BytesIO(content), stop_before_pixels=True)
                if (
                    data["identifier_kind"] != "facility"
                    or not settings.PACS_ASSIGNING_AUTHORITY
                    or str(getattr(source, "IssuerOfPatientID", ""))
                    != settings.PACS_ASSIGNING_AUTHORITY
                ):
                    raise ValueError("Unapproved DICOM assigning authority")
                source_birth = datetime.strptime(str(source.PatientBirthDate), "%Y%m%d").date()
                confirm_report_patient(
                    patient,
                    {
                        "identifier_kind": "facility",
                        "identifier_value": str(source.PatientID),
                        "source_birth_date": source_birth,
                    },
                )
                derivative, study, series, instance = deidentify(content, namespace)
            except (ValueError, AttributeError, KeyError, TypeError, InvalidDicomError) as exc:
                raise ValidationError(
                    "DICOM input is unsupported or privacy metadata is insufficient."
                ) from exc
            if PacsStudyLink.objects.filter(study_uid=study).exists():
                return Response({"code": "single_instance_study_conflict"}, status=409)
            boundary = "claria-synthetic-stow"
            body = (
                f"--{boundary}\r\nContent-Type: application/dicom\r\n\r\n".encode()
                + derivative
                + f"\r\n--{boundary}--\r\n".encode()
            )
            result, _ = pacs_request(
                "POST",
                "/studies",
                body=body,
                content_type=f'multipart/related; type="application/dicom"; boundary={boundary}',
            )
            try:
                response = json.loads(result)
                returned = [
                    entry["00081155"]["Value"][0] for entry in response["00081199"]["Value"]
                ]
                if returned != [instance] or response.get("00081198", {}).get("Value"):
                    raise ValueError("Unconfirmed store")
            except (ValueError, KeyError, TypeError) as exc:
                raise IntegrationUnavailable() from exc
            link = PacsStudyLink.objects.create(
                version=version,
                author=request.user,
                study_uid=study,
                series_uid=series,
                instance_uid=instance,
                derivative_sha256=hashlib.sha256(derivative).hexdigest(),
            )
            audit(request.user, "interop.pacs_stored", link.pk, patient.organization)
        return Response(
            {
                "study_uid": study,
                "series_uid": series,
                "instance_uid": instance,
                "privacy": "pseudonymized, not proven anonymous",
            },
            status=201,
        )


def authorized_links(user):
    return PacsStudyLink.objects.filter(
        version__document__in=visible_documents(user, "download"),
        version__document__patient__in=clinical_patients(user),
        version__purged_at__isnull=True,
    )


class DicomWebView(InputView):
    schema = InteropPathSchema()

    @extend_schema(responses={(200, "application/dicom+json"): OpenApiTypes.OBJECT})
    def get(self, request, study_uid=None, suffix=""):
        require_enabled()
        if not verified_professional(request.user):
            raise PermissionDenied()
        rate_limit(request, "pacs-read", limit=180, by_user=True)
        if study_uid is None:
            if set(request.query_params) - {
                "StudyInstanceUID",
                "limit",
                "includefield",
            } or not request.query_params.get("StudyInstanceUID"):
                raise ValidationError(
                    "One mapped study UID is required; unrestricted study listing is disabled."
                )
            study_uid = request.query_params["StudyInstanceUID"]
            mode = "study"
        else:
            if request.query_params:
                raise ValidationError("Unsupported DICOMweb query.")
            mode = "path"
        if len(study_uid) > 64 or not re.fullmatch(UID, study_uid):
            raise ValidationError("Invalid study UID.")
        link = get_object_or_404(
            authorized_links(request.user).select_related(
                "version__document__patient__organization"
            ),
            study_uid=study_uid,
        )
        prefix = f"/studies/{study_uid}"
        frame_path = f"series/{link.series_uid}/instances/{link.instance_uid}/frames/1"
        allowed = {
            "series",
            f"series/{link.series_uid}/instances",
            "metadata",
            f"series/{link.series_uid}/metadata",
            f"series/{link.series_uid}/instances/{link.instance_uid}/metadata",
            frame_path,
        }
        if mode == "path" and suffix not in allowed:
            raise Http404
        path = (
            "/studies?" + urlencode({"StudyInstanceUID": study_uid})
            if mode == "study"
            else prefix + "/" + suffix
        )
        pixels = suffix == frame_path
        body, media_type = pacs_request(
            "GET",
            path,
            accept='multipart/related; type="application/octet-stream"'
            if pixels
            else "application/dicom+json",
        )
        if not pixels:
            try:
                objects = json.loads(body)
                if not isinstance(objects, list) or len(objects) > 100:
                    raise ValueError
                for item in objects:
                    required = (
                        "0020000D"
                        if mode == "study"
                        else ("0020000E" if suffix == "series" else "00080018")
                    )
                    expected_uid = {
                        "0020000D": link.study_uid,
                        "0020000E": link.series_uid,
                        "00080018": link.instance_uid,
                    }[required]
                    if not isinstance(item, dict) or item.get(required, {}).get("Value") != [
                        expected_uid
                    ]:
                        raise ValueError("Missing mapped image identifier")
                    for tag, expected in (
                        ("0020000D", link.study_uid),
                        ("0020000E", link.series_uid),
                        ("00080018", link.instance_uid),
                    ):
                        if tag in item and item[tag].get("Value") != [expected]:
                            raise ValueError("Unexpected mapped image")
                    # Never expose raw archive BulkDataURI/URLs or free-text metadata.
                    safe = {tag: value for tag, value in item.items() if tag in DICOM_JSON_TAGS}
                    if any(
                        not isinstance(value, dict)
                        or value.get("vr") == "SQ"
                        or "BulkDataURI" in value
                        or "InlineBinary" in value
                        for value in safe.values()
                    ):
                        raise ValueError("Unsafe archive metadata representation")
                    item.clear()
                    item.update(safe)
                body = json.dumps(objects).encode()
            except (ValueError, TypeError, AttributeError) as exc:
                raise IntegrationUnavailable() from exc
            media_type = "application/dicom+json"
        elif not media_type.startswith("multipart/related"):
            raise IntegrationUnavailable()
        audit(
            request.user, "interop.pacs_read", link.pk, link.version.document.patient.organization
        )
        response = HttpResponse(body, content_type=media_type)
        response["Cache-Control"] = "no-store"
        return response


DICOM_JSON_TAGS = frozenset(
    {
        "00080016",
        "00080018",
        "00080020",
        "00080030",
        "00080050",
        "00080060",
        "00080061",
        "00180050",
        "00181164",
        "0020000D",
        "0020000E",
        "00200010",
        "00200011",
        "00200013",
        "00200032",
        "00200037",
        "00201206",
        "00201208",
        "00280002",
        "00280004",
        "00280008",
        "00280010",
        "00280011",
        "00280030",
        "00280100",
        "00280101",
        "00280102",
        "00280103",
        "00281050",
        "00281051",
        "00281052",
        "00281053",
        "20500020",
    }
)
