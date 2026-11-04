from django.db import transaction
from django.db.models import Exists, OuterRef, Q, Subquery, Value
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from identity import analysis, clinical, clinical_storage
from identity.clinical_formats import validated_text
from identity.models import ClinicalDocument, ClinicalDocumentVersion, ClinicalFolder
from identity.security import audit, rate_limit
from identity.services import verified_professional, visible_patients
from identity.views import InputView


class UploadInput(serializers.Serializer):
    file = serializers.FileField()
    folder = serializers.UUIDField(required=False)
    title = serializers.CharField(max_length=160)
    kind = serializers.ChoiceField(choices=ClinicalDocument.Kind.choices, required=False)


class VersionOutput(serializers.ModelSerializer):
    can_download = serializers.BooleanField(read_only=True)
    can_edit = serializers.BooleanField(read_only=True)
    can_share = serializers.BooleanField(read_only=True)
    can_analyze = serializers.BooleanField(read_only=True)
    folder = serializers.UUIDField(source="document.folder_id", read_only=True, allow_null=True)

    class Meta:
        model = ClinicalDocumentVersion
        fields = (
            "id",
            "document",
            "number",
            "title",
            "media_type",
            "size",
            "created_at",
            "can_download",
            "can_edit",
            "can_share",
            "can_analyze",
            "folder",
        )


def metadata():
    return ClinicalDocumentVersion.objects.defer(
        "ciphertext", "wrapped_key", "search_tokens"
    ).select_related("document__patient__organization")


def with_actions(versions, user):
    analyze: Value | Exists = Value(False)
    if analysis.enabled() and analysis.eligible(user):
        analyze = Exists(
            ClinicalDocumentVersion.objects.filter(
                pk=OuterRef("pk"),
                document__patient__in=clinical.clinical_patients(user),
                document__kind="report",
                media_type__in=["application/pdf", "image/png", "image/jpeg"],
            )
        )
    return versions.annotate(
        can_analyze=analyze,
        can_download=Exists(
            clinical.visible_documents(user, "download").filter(pk=OuterRef("document_id"))
        ),
        can_edit=Exists(
            ClinicalDocument.objects.filter(
                pk=OuterRef("document_id"),
                author=user,
                patient__in=clinical.clinical_patients(user),
            )
        ),
        can_share=Exists(
            ClinicalDocument.objects.filter(
                pk=OuterRef("document_id"),
                patient__in=visible_patients(user),
                patient__account__isnull=False,
            ).exclude(kind=ClinicalDocument.Kind.PSYCHOLOGY)
        ),
    )


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
        search_tokens=upload["search_tokens"],
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
    if file.content_type not in (detected, "application/octet-stream"):
        raise ValidationError("Declared type does not match file signature.")
    clinical.scan(content)
    text = validated_text(content, detected)
    return {
        **upload,
        "media_type": detected,
        "bytes": content,
        "search_tokens": clinical.search_tokens(text, patient.organization_id),
        "sealed": clinical.seal(content, patient.organization_id),
    }


class FolderInput(serializers.Serializer):
    title = serializers.CharField(max_length=100)
    parent_folder = serializers.UUIDField(source="parent", required=False)


class FolderOutput(serializers.ModelSerializer):
    class Meta:
        model = ClinicalFolder
        fields = ("id", "title", "parent")


class FoldersView(InputView):
    serializer_class = FolderInput

    @extend_schema(responses=FolderOutput(many=True))
    def get(self, request, patient_id):
        patient = get_object_or_404(visible_patients(request.user), pk=patient_id)
        folders = ClinicalFolder.objects.filter(patient=patient).order_by("title", "pk")
        page = self.paginate_queryset(folders)
        return self.get_paginated_response(FolderOutput(page, many=True).data)

    @transaction.atomic
    @extend_schema(responses={201: FolderOutput})
    def post(self, request, patient_id):
        if not verified_professional(request.user):
            raise PermissionDenied()
        patient = get_object_or_404(clinical.clinical_patients(request.user), pk=patient_id)
        data = self.data(request)
        parent = None
        if data.get("parent"):
            parent = get_object_or_404(ClinicalFolder, pk=data["parent"], patient=patient)
            ancestor = parent
            for _ in range(7):
                next_ancestor = ancestor.parent
                if next_ancestor is None:
                    break
                ancestor = next_ancestor
            else:
                raise ValidationError("Maximum folder depth reached.")
        folder = ClinicalFolder.objects.create(patient=patient, parent=parent, title=data["title"])
        audit(request.user, "clinical.folder_created", folder.pk, patient.organization)
        return Response(FolderOutput(folder).data, status=201)


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
            predicate = Q(title__icontains=query)
            organization_id = documents.values_list("patient__organization_id", flat=True).first()
            tokens = clinical.search_tokens(query, organization_id)
            if tokens:
                predicate |= Q(search_tokens__contains=tokens)
            versions = versions.filter(predicate)
        page = self.paginate_queryset(
            with_actions(versions, request.user).order_by("-created_at", "-pk")
        )
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
        folder = None
        if upload.get("folder"):
            folder = get_object_or_404(ClinicalFolder, pk=upload["folder"], patient=patient)
        with transaction.atomic():
            document = ClinicalDocument.objects.create(
                patient=patient,
                author=request.user,
                kind=upload.get("kind", "other"),
                folder=folder,
            )
            version = store_version(document, upload, 1)
            audit(request.user, "clinical.created", version.pk, patient.organization)
        return Response(
            VersionOutput(with_actions(metadata(), request.user).get(pk=version.pk)).data,
            status=201,
        )


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
        page = self.paginate_queryset(
            with_actions(metadata().filter(document=document), request.user).order_by("-number")
        )
        assert page is not None  # Pagination is configured for all clinical lists.
        for version in page:
            audit(request.user, "clinical.metadata_read", version.pk, document.patient.organization)
        return self.get_paginated_response(VersionOutput(page, many=True).data)

    @extend_schema(responses={201: VersionOutput})
    def post(self, request, document_id):
        rate_limit(request, "clinical-upload", limit=12)
        document = get_object_or_404(self.editable(request), pk=document_id)
        upload = prepared_upload(request, document.patient)
        if "folder" in upload and upload["folder"] != document.folder_id:
            raise ValidationError("Document folder cannot change between versions.")
        if "kind" in upload and upload["kind"] != document.kind:
            raise ValidationError("Document category cannot change between versions.")
        with transaction.atomic():
            document = get_object_or_404(self.editable(request).select_for_update(), pk=document_id)
            version = store_version(document, upload, latest(document).number + 1)
            audit(
                request.user, "clinical.version_created", version.pk, document.patient.organization
            )
        return Response(
            VersionOutput(with_actions(metadata(), request.user).get(pk=version.pk)).data,
            status=201,
        )

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
        plaintext = clinical_storage.read_content(version)
        audit(request.user, "clinical.downloaded", version.pk, organization)
        response = HttpResponse(plaintext, content_type="application/octet-stream")
        response["Content-Disposition"] = 'attachment; filename="clinical-document"'
        response["X-Content-Type-Options"] = "nosniff"
        return response


class FhirJSONRenderer(JSONRenderer):
    media_type = "application/fhir+json"
    format = "fhir"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = (renderer_context or {}).get("response")
        if response is not None and response.status_code >= 400:
            code = {403: "forbidden", 404: "not-found", 406: "not-supported"}.get(
                response.status_code, "processing"
            )
            data = {
                "resourceType": "OperationOutcome",
                "issue": [{"severity": "error", "code": code}],
            }
        return super().render(data, accepted_media_type, renderer_context)


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
                            for resource in (
                                "DocumentReference",
                                "Patient",
                                "Organization",
                                "Practitioner",
                                "Consent",
                                "DiagnosticReport",
                                "Observation",
                            )
                        ],
                    }
                ],
            },
            content_type="application/fhir+json",
        )
