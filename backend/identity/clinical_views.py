from cryptography.fernet import Fernet, InvalidToken
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from identity import clinical
from identity.models import ClinicalDocument, ClinicalDocumentVersion
from identity.security import audit, rate_limit
from identity.services import verified_professional, visible_patients
from identity.views import InputView


class UploadInput(serializers.Serializer):
    file = serializers.FileField()
    title = serializers.CharField(max_length=160)
    kind = serializers.ChoiceField(choices=ClinicalDocument.Kind.choices, required=False)


class VersionOutput(serializers.ModelSerializer):
    class Meta:
        model = ClinicalDocumentVersion
        fields = ("id", "document", "number", "title", "media_type", "size", "created_at")


def metadata():
    return ClinicalDocumentVersion.objects.defer("ciphertext", "wrapped_key")


def latest(document):
    version = metadata().filter(document=document).order_by("-number").first()
    if version is None:
        raise Http404
    return version


def store_version(document, upload, number):
    return ClinicalDocumentVersion.objects.create(
        document=document,
        number=number,
        title=upload["title"],
        media_type=upload["media_type"],
        size=len(upload["bytes"]),
        **upload["sealed"],
    )


def prepared_upload(request, patient):
    data = UploadInput(data=request.data)
    data.is_valid(raise_exception=True)
    upload = data.validated_data
    file = upload["file"]
    if file.size > clinical.MAX_BYTES:
        raise ValidationError("Maximum file size is 10 MiB.")
    content = file.read(clinical.MAX_BYTES + 1)
    if len(content) > clinical.MAX_BYTES:
        raise ValidationError("Maximum file size is 10 MiB.")
    detected = clinical.media_type(content)
    if file.content_type != detected:
        raise ValidationError("Declared type does not match file signature.")
    clinical.scan(content)
    return {
        **upload,
        "media_type": detected,
        "bytes": content,
        "sealed": clinical.seal(content, patient.organization_id),
    }


class DocumentsView(InputView):
    serializer_class = UploadInput
    parser_classes = [MultiPartParser]

    @extend_schema(responses=VersionOutput(many=True))
    def get(self, request, patient_id):
        documents = clinical.visible_documents(request.user).filter(patient_id=patient_id)

        current = metadata().filter(document_id=OuterRef("document_id")).order_by("-number")
        versions = metadata().filter(document__in=documents, pk=Subquery(current.values("pk")[:1]))
        query = request.query_params.get("q", "").strip()
        if len(query) > 160:
            raise ValidationError("Search query too long.")
        if query:
            versions = versions.filter(title__icontains=query)
        page = self.paginate_queryset(versions.order_by("-created_at", "-pk"))
        assert page is not None  # Pagination is configured for all clinical lists.
        for version in page:
            audit(
                request.user,
                "clinical.metadata_read",
                version.pk,
                version.document.patient.organization,
            )
        return self.get_paginated_response(VersionOutput(page, many=True).data)

    @extend_schema(responses={201: VersionOutput})
    def post(self, request, patient_id):
        rate_limit(request, "clinical-upload", limit=12)
        if not verified_professional(request.user):
            raise PermissionDenied()
        patient = get_object_or_404(clinical.clinical_patients(request.user), pk=patient_id)
        upload = prepared_upload(request, patient)
        with transaction.atomic():
            document = ClinicalDocument.objects.create(
                patient=patient, author=request.user, kind=upload.get("kind", "other")
            )
            version = store_version(document, upload, 1)
            audit(request.user, "clinical.created", version.pk, patient.organization)
        return Response(VersionOutput(version).data, status=201)


class DocumentView(InputView):
    serializer_class = UploadInput
    parser_classes = [MultiPartParser]

    def editable(self, request):
        if not verified_professional(request.user):
            raise PermissionDenied()
        return ClinicalDocument.objects.filter(
            author=request.user,
            deleted_at__isnull=True,
            patient__in=clinical.clinical_patients(request.user),
        )

    @extend_schema(responses=VersionOutput(many=True))
    def get(self, request, document_id):
        document = get_object_or_404(clinical.visible_documents(request.user), pk=document_id)
        page = self.paginate_queryset(metadata().filter(document=document).order_by("-number"))
        assert page is not None  # Pagination is configured for all clinical lists.
        for version in page:
            audit(request.user, "clinical.metadata_read", version.pk, document.patient.organization)
        return self.get_paginated_response(VersionOutput(page, many=True).data)

    @extend_schema(responses={201: VersionOutput})
    def post(self, request, document_id):
        rate_limit(request, "clinical-upload", limit=12)
        document = get_object_or_404(self.editable(request), pk=document_id)
        upload = prepared_upload(request, document.patient)
        if "kind" in upload and upload["kind"] != document.kind:
            raise ValidationError("Document category cannot change between versions.")
        with transaction.atomic():
            document = get_object_or_404(self.editable(request).select_for_update(), pk=document_id)
            version = store_version(document, upload, latest(document).number + 1)
            audit(
                request.user, "clinical.version_created", version.pk, document.patient.organization
            )
        return Response(VersionOutput(version).data, status=201)

    def delete(self, request, document_id):
        with transaction.atomic():
            document = get_object_or_404(self.editable(request).select_for_update(), pk=document_id)
            document.deleted_at = timezone.now()
            document.save(update_fields=["deleted_at"])
            audit(request.user, "clinical.archived", document.pk, document.patient.organization)
        return Response(status=204)


class DownloadView(InputView):
    serializer_class = VersionOutput

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    def get(self, request, version_id):
        version = get_object_or_404(
            ClinicalDocumentVersion.objects.select_related("document__patient__organization"),
            pk=version_id,
            document__in=clinical.visible_documents(request.user, permission="download"),
        )
        organization = version.document.patient.organization
        try:
            key = clinical.tenant_cipher(organization.pk).decrypt(bytes(version.wrapped_key))
            plaintext = Fernet(key).decrypt(bytes(version.ciphertext))
        except InvalidToken as exc:
            raise clinical.DocumentUnavailable() from exc
        audit(request.user, "clinical.downloaded", version.pk, organization)
        response = HttpResponse(plaintext, content_type="application/octet-stream")
        response["Content-Disposition"] = 'attachment; filename="clinical-document"'
        response["X-Content-Type-Options"] = "nosniff"
        return response


class FhirJSONRenderer(JSONRenderer):
    media_type = "application/fhir+json"


class FhirDocumentView(InputView):
    renderer_classes = [FhirJSONRenderer, JSONRenderer]
    serializer_class = VersionOutput

    @extend_schema(responses={(200, "application/fhir+json"): OpenApiTypes.OBJECT})
    def get(self, request, resource_id):
        version = get_object_or_404(
            metadata().select_related("document__patient__organization"),
            pk=resource_id,
            document__in=clinical.visible_documents(request.user),
        )
        audit(request.user, "clinical.fhir_read", version.pk, version.document.patient.organization)
        attachment = {
            "contentType": version.media_type,
            "title": version.title,
            "size": version.size,
        }
        if (
            clinical.visible_documents(request.user, "download")
            .filter(pk=version.document_id)
            .exists()
        ):
            attachment["url"] = f"/api/v1/clinical/versions/{version.pk}/download/"
        subject = {}
        if visible_patients(request.user).filter(pk=version.document.patient_id).exists():
            subject = {"subject": {"reference": f"Patient/{version.document.patient_id}"}}
        return JsonResponse(
            {
                **subject,
                "resourceType": "DocumentReference",
                "id": str(version.pk),
                "status": "current" if latest(version.document).pk == version.pk else "superseded",
                "date": version.created_at.isoformat(),
                "content": [{"attachment": attachment}],
            },
            content_type="application/fhir+json",
        )


class FhirPatientView(InputView):
    serializer_class = VersionOutput
    renderer_classes = [FhirJSONRenderer, JSONRenderer]

    @extend_schema(responses={(200, "application/fhir+json"): OpenApiTypes.OBJECT})
    def get(self, request, resource_id):
        patient = get_object_or_404(
            visible_patients(request.user).select_related("organization"), pk=resource_id
        )
        audit(request.user, "clinical.fhir_patient_read", patient.pk, patient.organization)
        return JsonResponse(
            {
                "resourceType": "Patient",
                "id": str(patient.pk),
                "name": [{"family": patient.last_name, "given": [patient.first_name]}],
                "birthDate": patient.birth_date.isoformat(),
            },
            content_type="application/fhir+json",
        )


class FhirMetadataView(InputView):
    renderer_classes = [FhirJSONRenderer, JSONRenderer]
    serializer_class = VersionOutput

    @extend_schema(responses={(200, "application/fhir+json"): OpenApiTypes.OBJECT})
    def get(self, request):
        return JsonResponse(
            {
                "resourceType": "CapabilityStatement",
                "status": "draft",
                "date": "2026-11-04",
                "kind": "capability",
                "software": {"name": "Clarìa"},
                "fhirVersion": "4.0.1",
                "format": ["application/fhir+json"],
                "rest": [
                    {
                        "mode": "server",
                        "resource": [
                            {"type": resource, "interaction": [{"code": "read"}]}
                            for resource in ("DocumentReference", "Patient")
                        ],
                    }
                ],
            },
            content_type="application/fhir+json",
        )
