import hashlib

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from identity.analysis import authorized_jobs, decode, eligible, enabled, encode
from identity.analysis_pipeline import DISCLAIMER, PIPELINE, suggested_text
from identity.clinical import clinical_patients
from identity.models import (
    AnalysisJob,
    AnalysisOpinion,
    AnalysisPublication,
    AnalysisReview,
    ClinicalDocumentVersion,
    Membership,
)
from identity.security import audit, rate_limit
from identity.views import InputView


class JobOutput(serializers.ModelSerializer):
    class Meta:
        model = AnalysisJob
        fields = ("id", "state", "pipeline", "input_hash", "created_at")


class AnalysisReviewInput(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["accept", "modify", "reject"])
    text = serializers.CharField(max_length=8000)
    confirmed = serializers.BooleanField(default=False)


def require_reviewer(request):
    if (
        not enabled()
        or not eligible(request.user)
        or request.session.get("mfa_version") != request.user.auth_version
    ):
        raise PermissionDenied()


class JobsView(InputView):
    serializer_class = JobOutput

    @extend_schema(responses=JobOutput(many=True))
    def get(self, request, version_id):
        require_reviewer(request)
        rows = authorized_jobs(request.user).filter(version_id=version_id).order_by("-created_at")
        page = self.paginate_queryset(
            rows.select_related("version__document__patient__organization")
        )
        for job in page or []:
            audit(
                request.user,
                "analysis.job_listed",
                job.pk,
                job.version.document.patient.organization,
            )
        return self.get_paginated_response(JobOutput(page, many=True).data)

    @extend_schema(request=None, responses={202: JobOutput})
    @transaction.atomic
    def post(self, request, version_id):
        require_reviewer(request)
        rate_limit(request, "analysis-start", limit=12)
        version = get_object_or_404(
            ClinicalDocumentVersion.objects.filter(
                document__patient__in=clinical_patients(request.user),
                document__kind="report",
                document__deleted_at__isnull=True,
                purged_at__isnull=True,
                media_type__in=["application/pdf", "image/png", "image/jpeg"],
            ).defer("ciphertext", "wrapped_key"),
            pk=version_id,
        )
        job, created = AnalysisJob.objects.get_or_create(
            version=version,
            pipeline=PIPELINE,
            defaults={
                "requested_by": request.user,
                "input_hash": version.sha256,
                "auth_version": request.user.auth_version,
            },
        )
        if created:
            audit(request.user, "analysis.requested", job.pk, version.document.patient.organization)
        return Response(JobOutput(job).data, status=202)


class JobView(InputView):
    serializer_class = JobOutput

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, job_id):
        require_reviewer(request)
        job = get_object_or_404(authorized_jobs(request.user), pk=job_id)
        output = dict(JobOutput(job).data)
        document = job.version.document
        if hasattr(job, "draft"):
            output["draft"] = decode(job.draft, document)
            output["disclaimer"] = DISCLAIMER
            output["suggestion"] = suggested_text(output["draft"])
            output["draft_created_at"] = job.draft.created_at
            if job.draft.model_id:
                model = job.draft.model
                output["model"] = {
                    "name": model.name,
                    "revision": model.revision,
                    "checksum": model.checksum,
                }
        if hasattr(job, "review"):
            review = job.review
            output["decision"] = review.decision
            if hasattr(review, "opinion"):
                opinion = review.opinion
                output["opinion"] = {
                    "id": str(opinion.pk),
                    "published": hasattr(opinion, "analysispublication"),
                }
        audit(request.user, "analysis.read", job.pk, document.patient.organization)
        return Response(output)


class ReviewView(InputView):
    serializer_class = AnalysisReviewInput

    @extend_schema(responses={201: OpenApiTypes.OBJECT})
    @transaction.atomic
    def post(self, request, job_id):
        require_reviewer(request)
        data = self.data(request)
        job = get_object_or_404(authorized_jobs(request.user).select_for_update(), pk=job_id)
        if job.state != "ready" or hasattr(job, "review"):
            return Response({"code": "review_conflict"}, status=409)
        decision = data["decision"]
        if decision != "reject" and not data["confirmed"]:
            raise ValidationError("Explicit attestation is required.")
        if decision == "accept":
            suggestion = suggested_text(decode(job.draft, job.version.document))
            if not suggestion or data["text"] != suggestion:
                raise ValidationError("Use modify to attest a different text.")
        organization = job.version.document.patient.organization
        review = AnalysisReview.objects.create(
            job=job,
            author=request.user,
            decision=decision,
            **encode({"reason": data["text"]} if decision == "reject" else {}, organization.pk),
        )
        output = {"decision": decision}
        if decision != "reject":
            sealed = encode({"text": data["text"]}, organization.pk)
            digest = hashlib.sha256(
                f"{job.pk}:{job.input_hash}:{request.user.pk}:{review.created_at.isoformat()}:{sealed['sha256']}".encode()
            ).hexdigest()
            opinion = AnalysisOpinion.objects.create(
                review=review, attestation_hash=digest, **sealed
            )
            output["opinion"] = str(opinion.pk)
        audit(request.user, "analysis." + decision, job.pk, organization)
        return Response(output, status=201)


class PublishView(InputView):
    serializer_class = JobOutput

    @extend_schema(request=None, responses={204: None})
    @transaction.atomic
    def post(self, request, opinion_id):
        require_reviewer(request)
        opinion = get_object_or_404(
            AnalysisOpinion.objects.select_for_update().filter(
                review__job__in=authorized_jobs(request.user),
                review__author=request.user,
            ),
            pk=opinion_id,
        )
        patient = opinion.review.job.version.document.patient
        if not patient.account_id:
            raise ValidationError("Link the patient account before publication.")
        _, created = AnalysisPublication.objects.get_or_create(
            opinion=opinion, defaults={"author": request.user, "recipient_id": patient.account_id}
        )
        if created:
            audit(request.user, "analysis.published", opinion.pk, patient.organization)
        return Response(status=204)


class PublishedOpinionsView(InputView):
    serializer_class = JobOutput

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, patient_id):
        opinions = AnalysisOpinion.objects.filter(
            analysispublication__recipient=request.user,
            review__job__version__document__patient_id=patient_id,
            review__job__version__document__patient__account=request.user,
            review__job__version__document__deleted_at__isnull=True,
            review__job__version__purged_at__isnull=True,
        ).order_by("-created_at", "-pk")
        page = self.paginate_queryset(opinions)
        results = []
        for opinion in page or []:
            document = opinion.review.job.version.document
            results.append(
                {
                    "id": str(opinion.pk),
                    "created_at": opinion.created_at,
                    "attestation_hash": opinion.attestation_hash,
                    "author": str(opinion.review.author_id),
                    "attested_at": opinion.review.created_at,
                    **decode(opinion, document),
                }
            )
            audit(request.user, "analysis.opinion_read", opinion.pk, document.patient.organization)
        return self.get_paginated_response(results)


class AnalysisMetricsView(InputView):
    serializer_class = JobOutput

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, org_id):
        if not enabled() or request.session.get("mfa_version") != request.user.auth_version:
            raise PermissionDenied()
        get_object_or_404(
            Membership, user=request.user, organization_id=org_id, active=True, role="admin"
        )
        metrics = (
            AnalysisReview.objects.filter(job__version__document__patient__organization_id=org_id)
            .values(
                "job__pipeline",
                "job__draft__model__name",
                "job__draft__model__revision",
                "job__draft__model__checksum",
            )
            .annotate(
                total=Count("pk"),
                modified=Count("pk", filter=Q(decision="modify")),
                rejected=Count("pk", filter=Q(decision="reject")),
            )
        )
        return Response(
            [
                {
                    **row,
                    "modify_rate": row["modified"] / row["total"],
                    "reject_rate": row["rejected"] / row["total"],
                }
                for row in metrics
            ]
        )
