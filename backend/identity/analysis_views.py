import base64
import binascii
import hashlib

from django.db import transaction
from django.db.models import Avg, Count, F, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from identity.analysis import adult_cutoff, authorized_jobs, decode, eligible, enabled, encode
from identity.analysis_pipeline import DISCLAIMER, PIPELINE, suggested_text
from identity.analysis_registry import current_policy, current_policy_jobs
from identity.analysis_signing import signing_content, verifier
from identity.clinical import clinical_patients
from identity.models import (
    AnalysisIncident,
    AnalysisJob,
    AnalysisOpinion,
    AnalysisPublication,
    AnalysisReview,
    AnalysisReviewSession,
    AnalysisSignature,
    ClinicalDocumentVersion,
    Membership,
    Organization,
)
from identity.patient_identification import IdentifierInput, confirm_report_patient
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
    confirmed_rows = serializers.ListField(
        child=serializers.CharField(max_length=20),
        max_length=100,
        default=list,
    )
    source_checked = serializers.BooleanField(default=False)


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
                document__patient__birth_date__lte=adult_cutoff(),
                document__kind="report",
                document__deleted_at__isnull=True,
                purged_at__isnull=True,
                media_type__in=["application/pdf", "image/png", "image/jpeg"],
            ).defer("ciphertext", "wrapped_key"),
            pk=version_id,
        )
        organization = version.document.patient.organization
        Organization.objects.select_for_update().get(pk=organization.pk)
        policy = current_policy(organization.pk)
        if policy is None:
            raise PermissionDenied("Approve the current model cards before analysis.")
        job, created = AnalysisJob.objects.get_or_create(
            version=version,
            pipeline=PIPELINE,
            policy=policy,
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
                    "signed": hasattr(opinion, "analysissignature"),
                    "digest": opinion.attestation_hash,
                    "signing_content": signing_content(
                        job, review, decode(opinion, document)["text"]
                    ),
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
        if job.state not in ("ready", "in_review") or hasattr(job, "review"):
            return Response({"code": "review_conflict"}, status=409)
        Organization.objects.select_for_update().get(
            pk=job.version.document.patient.organization_id
        )
        if current_policy(job.version.document.patient.organization_id) != job.policy:
            raise PermissionDenied()
        session = AnalysisReviewSession.objects.filter(job=job, author=request.user).first()
        if session is None:
            raise ValidationError("Start the review before recording a decision.")
        draft = decode(job.draft, job.version.document)
        decision = data["decision"]
        if decision != "reject" and not data["confirmed"]:
            raise ValidationError("Explicit attestation is required.")
        if decision != "reject":
            rows = draft.get("rows", [])
            required = {row["id"] for row in rows if row.get("requires_confirmation", True)}
            confirmed = data["confirmed_rows"]
            known = {row["id"] for row in rows}
            if (
                not rows
                or not data["source_checked"]
                or draft.get("notices")
                or len(confirmed) != len(set(confirmed))
                or set(confirmed) - known
                or required - set(confirmed)
            ):
                raise ValidationError("Verify all uncertain source evidence before attesting.")
        if decision == "accept":
            suggestion = suggested_text(decode(job.draft, job.version.document))
            if not suggestion or data["text"] != suggestion:
                raise ValidationError("Use modify to attest a different text.")
        organization = job.version.document.patient.organization
        review = AnalysisReview.objects.create(
            job=job,
            author=request.user,
            decision=decision,
            **encode(
                {"reason": data["text"], "session": str(session.pk)}
                if decision == "reject"
                else {
                    "confirmed_rows": data["confirmed_rows"],
                    "source_checked": data["source_checked"],
                    "session": str(session.pk),
                },
                organization.pk,
            ),
        )
        output = {"decision": decision}
        if decision != "reject":
            sealed = encode({"text": data["text"]}, organization.pk)
            digest = hashlib.sha256(signing_content(job, review, data["text"]).encode()).hexdigest()
            opinion = AnalysisOpinion.objects.create(
                review=review, attestation_hash=digest, **sealed
            )
            output["opinion"] = str(opinion.pk)
        job.state = {"accept": "accepted", "modify": "modified", "reject": "rejected"}[decision]
        job.save(update_fields=["state"])
        audit(request.user, "analysis." + decision, job.pk, organization)
        return Response(output, status=201)


class PublishView(InputView):
    serializer_class = JobOutput

    @extend_schema(request=None, responses={204: None})
    @transaction.atomic
    def post(self, request, opinion_id):
        require_reviewer(request)
        candidate = get_object_or_404(
            AnalysisOpinion.objects.filter(
                review__job__in=authorized_jobs(request.user),
                review__author=request.user,
            ),
            pk=opinion_id,
        )
        patient = candidate.review.job.version.document.patient
        Organization.objects.select_for_update().get(pk=patient.organization_id)
        opinion = get_object_or_404(
            AnalysisOpinion.objects.select_for_update().filter(
                review__job__in=authorized_jobs(request.user),
                review__author=request.user,
            ),
            pk=opinion_id,
        )
        if current_policy(patient.organization_id) != opinion.review.job.policy:
            raise PermissionDenied()
        if not hasattr(opinion, "analysissignature"):
            return Response({"code": "verified_signature_required"}, status=409)
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
            analysissignature__isnull=False,
            review__job__in=current_policy_jobs(),
            review__job__version__document__patient_id=patient_id,
            review__job__version__document__patient__account=request.user,
            review__job__version__document__deleted_at__isnull=True,
            review__job__version__purged_at__isnull=True,
        ).order_by("-created_at", "-pk")
        if not enabled():
            opinions = opinions.none()
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
        sessions = AnalysisReviewSession.objects.filter(
            job_id=OuterRef("job_id"), author_id=OuterRef("author_id")
        ).values("created_at")[:1]
        metrics = (
            AnalysisReview.objects.filter(job__version__document__patient__organization_id=org_id)
            .annotate(review_started_at=Subquery(sessions))
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
                average_review_duration=Avg(F("created_at") - F("review_started_at")),
                average_extracted_rows=Avg("job__extraction_rows"),
                average_uncertain_rows=Avg("job__uncertain_rows"),
            )
        )
        audit(request.user, "analysis.metrics_read", org_id)
        return Response(
            [
                {
                    **row,
                    "average_review_duration": (
                        row["average_review_duration"].total_seconds()
                        if row["average_review_duration"] is not None
                        else None
                    ),
                    "modify_rate": row["modified"] / row["total"],
                    "reject_rate": row["rejected"] / row["total"],
                }
                for row in metrics
            ]
        )


class StartReviewView(InputView):
    serializer_class = JobOutput

    @extend_schema(request=None, responses=JobOutput)
    @transaction.atomic
    def post(self, request, job_id):
        require_reviewer(request)
        job = get_object_or_404(authorized_jobs(request.user).select_for_update(), pk=job_id)
        if job.state not in ("ready", "in_review") or hasattr(job, "review"):
            return Response({"code": "review_conflict"}, status=409)
        _, created = AnalysisReviewSession.objects.get_or_create(job=job, author=request.user)
        job.state = "in_review"
        job.save(update_fields=["state"])
        if created:
            audit(
                request.user,
                "analysis.review_started",
                job.pk,
                job.version.document.patient.organization,
            )
        return Response(JobOutput(job).data)


class SignatureInput(IdentifierInput):
    artifact = serializers.CharField(max_length=65536, trim_whitespace=False)


class SignOpinionView(InputView):
    serializer_class = SignatureInput

    @extend_schema(responses={201: OpenApiTypes.OBJECT})
    def post(self, request, opinion_id):
        require_reviewer(request)
        rate_limit(request, "clinical-signature", limit=12, by_user=True)
        opinion = get_object_or_404(
            AnalysisOpinion.objects.filter(
                review__job__in=authorized_jobs(request.user),
                review__author=request.user,
            ).select_related("review__job__version__document__patient__organization"),
            pk=opinion_id,
        )
        data = self.data(request)
        confirm_report_patient(opinion.review.job.version.document.patient, data)
        try:
            artifact = base64.b64decode(data["artifact"], validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValidationError("Invalid signature artifact.") from exc
        if not artifact:
            raise ValidationError("A signed artifact is required.")
        proof = verifier().verify(
            artifact=artifact,
            expected_digest=opinion.attestation_hash,
            expected_signer_id=request.user.pk,
        )
        if (
            proof.signer_id != request.user.pk
            or proof.digest != opinion.attestation_hash
            or proof.format not in ("PAdES", "CAdES")
            or not proof.provider_reference
            or len(proof.provider_reference) > 160
            or timezone.is_naive(proof.signed_at)
            or proof.signed_at > timezone.now()
        ):
            raise ValidationError("Signature does not match the reviewed opinion.")
        patient = opinion.review.job.version.document.patient
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=patient.organization_id)
            opinion = get_object_or_404(
                AnalysisOpinion.objects.select_for_update().filter(
                    review__job__in=authorized_jobs(request.user),
                    review__author=request.user,
                ),
                pk=opinion_id,
            )
            confirm_report_patient(patient, data)
            _, created = AnalysisSignature.objects.get_or_create(
                opinion=opinion,
                defaults={
                    "signer": request.user,
                    "provider": proof.provider_reference,
                    "format": proof.format,
                    "signed_at": proof.signed_at,
                    **encode(
                        {"artifact": base64.b64encode(artifact).decode()}, patient.organization_id
                    ),
                },
            )
            if created:
                audit(request.user, "analysis.opinion_signed", opinion.pk, patient.organization)
        return Response({"signed": True}, status=201)


class AnalysisIncidentInput(serializers.Serializer):
    category = serializers.ChoiceField(
        choices=["incorrect_extraction", "missed_finding", "unexpected_output", "privacy", "other"]
    )
    note = serializers.CharField(max_length=2000)


class AnalysisIncidentView(InputView):
    serializer_class = AnalysisIncidentInput

    @extend_schema(responses={201: OpenApiTypes.OBJECT})
    @transaction.atomic
    def post(self, request, job_id):
        require_reviewer(request)
        job = get_object_or_404(authorized_jobs(request.user), pk=job_id)
        data = self.data(request)
        organization = job.version.document.patient.organization
        incident = AnalysisIncident.objects.create(
            job=job,
            reporter=request.user,
            category=data["category"],
            **encode({"note": data["note"]}, organization.pk),
        )
        audit(request.user, "analysis.incident_reported", incident.pk, organization)
        return Response({"id": incident.pk}, status=201)
