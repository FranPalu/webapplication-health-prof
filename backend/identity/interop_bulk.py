"""Asynchronous, consent-rechecked export of approved aggregate MeasureReports.

This is a restricted research export, not row-level patient bulk access.
"""

import json
from datetime import timedelta
from urllib.parse import urlencode

from celery import shared_task
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from identity.analysis import decode_tenant, encode
from identity.interop_oauth import ResearchInteropReady, SmartResearchAuthentication, fhir_base
from identity.interop_policy import require_enabled
from identity.models import (
    ResearchAccessRequest,
    ResearchBulkJob,
    ResearchBulkPayload,
    ResearchReleasedSnapshot,
)
from identity.research_archive import DATASET
from identity.research_exports import encode_export
from identity.research_release_views import ReleaseUnavailable, current_snapshot, research_admins
from identity.security import StrictSessionAuthentication, audit, rate_limit
from identity.views import InputView


def current_access(request, access_id):
    if isinstance(request.auth, dict) and "research_access" in request.auth:
        if str(request.auth["research_access"]) != str(access_id):
            raise ReleaseUnavailable()
        return get_object_or_404(
            ResearchAccessRequest.objects.select_for_update(), pk=access_id, status="approved"
        )
    return get_object_or_404(
        ResearchAccessRequest.objects.select_for_update().filter(
            organization_id__in=research_admins(request).values("organization_id"),
            status="approved",
        ),
        pk=access_id,
    )


def checked_job(request, job_id):
    require_enabled()
    job = get_object_or_404(
        ResearchBulkJob.objects.select_for_update().select_related("access__organization"),
        pk=job_id,
        requested_by=request.user,
        expires_at__gt=timezone.now(),
        auth_version=request.user.auth_version,
    )
    entry = current_access(request, job.access_id)
    checksum, _ = current_snapshot()
    if checksum != job.checksum or checksum != entry.checksum:
        raise ReleaseUnavailable()
    return job


class ResearchInteropView(InputView):
    authentication_classes = [SmartResearchAuthentication, StrictSessionAuthentication]
    permission_classes = [ResearchInteropReady]


class ResearchBulkStartView(ResearchInteropView):
    @extend_schema(responses={202: OpenApiTypes.OBJECT})
    @transaction.atomic
    def get(self, request):
        require_enabled()
        rate_limit(request, "research-bulk-start", limit=12, by_user=True)
        if (
            set(request.query_params) != {"_type", "access_request"}
            or request.query_params.get("_type") != "MeasureReport"
            or any(len(request.query_params.getlist(key)) != 1 for key in request.query_params)
            or request.headers.get("Prefer") != "respond-async"
        ):
            raise ValidationError(
                "Only approved aggregate MeasureReport export with respond-async is supported."
            )
        try:
            from uuid import UUID

            access_id = UUID(request.query_params["access_request"])
        except ValueError as exc:
            raise ValidationError("Invalid access request.") from exc
        entry = current_access(request, access_id)
        checksum, _ = current_snapshot()
        if checksum != entry.checksum:
            raise ReleaseUnavailable()
        job = ResearchBulkJob.objects.create(
            access=entry,
            requested_by=request.user,
            auth_version=request.user.auth_version,
            checksum=checksum,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        audit(request.user, "interop.research_bulk_requested", job.pk, entry.organization)
        transaction.on_commit(lambda: prepare_bulk.delay(str(job.pk)), robust=True)
        response = Response(status=202)
        response["Content-Location"] = f"/api/v1/interop/research-exports/{job.pk}/"
        response["Retry-After"] = "5"
        response["Cache-Control"] = "no-store"
        return response


@shared_task(ignore_result=True)
def prepare_bulk(job_id):
    from django.conf import settings

    from identity.interop_policy import enabled
    from identity.models import Membership

    if not enabled() or not settings.RESEARCH_EXPORT_ENABLED:
        return
    with transaction.atomic():
        job = (
            ResearchBulkJob.objects.select_for_update()
            .select_related("access__organization", "requested_by")
            .filter(pk=job_id, state="queued")
            .first()
        )
        if job is None:
            return
        actor, access = job.requested_by, job.access
        allowed = (
            actor.is_active
            and actor.email_verified
            and actor.mfa_enabled
            and actor.auth_version == job.auth_version
            and access.status == "approved"
            and job.expires_at > timezone.now()
            and Membership.objects.filter(
                organization=access.organization,
                user=actor,
                role="admin",
                active=True,
                organization__kind="research",
            ).exists()
        )
        if not allowed:
            job.state = "cancelled"
        else:
            try:
                checksum, rows = current_snapshot()
                if checksum != job.checksum or checksum != access.checksum:
                    raise ReleaseUnavailable()
                bundle, _, _ = encode_export(rows, "fhir")
                resources = [entry["resource"] for entry in json.loads(bundle)["entry"]]
                ndjson = "".join(
                    json.dumps(resource, separators=(",", ":")) + "\n" for resource in resources
                )
                ResearchBulkPayload.objects.create(
                    job=job,
                    row_count=len(resources),
                    **encode({"ndjson": ndjson}, access.organization_id),
                )
                job.state = "ready"
            except ReleaseUnavailable:
                job.state = "cancelled"
        job.save(update_fields=["state"])
        audit(actor, "interop.research_bulk_" + job.state, job.pk, access.organization)


class ResearchBulkStatusView(ResearchInteropView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    @transaction.atomic
    def get(self, request, job_id):
        job = checked_job(request, job_id)
        audit(request.user, "interop.research_bulk_polled", job.pk, job.access.organization)
        if job.state == "queued":
            response = Response(status=202)
            response["Retry-After"] = "5"
            return response
        if job.state != "ready":
            raise ReleaseUnavailable()
        return Response(
            {
                "transactionTime": job.created_at.isoformat(),
                "requiresAccessToken": True,
                "request": fhir_base()
                + "/$export?"
                + urlencode({"_type": "MeasureReport", "access_request": str(job.access_id)}),
                "output": [
                    {
                        "type": "MeasureReport",
                        "url": request.build_absolute_uri(
                            f"/api/v1/interop/research-exports/{job.pk}/MeasureReport.ndjson"
                        ),
                    }
                ],
                "error": [],
                "scope": "Approved aggregate projection only; no patient-level export",
            }
        )


class ResearchBulkFileView(ResearchInteropView):
    @extend_schema(responses={(200, "application/fhir+ndjson"): OpenApiTypes.BINARY})
    @transaction.atomic
    def get(self, request, job_id):
        job = checked_job(request, job_id)
        if job.state != "ready":
            raise ReleaseUnavailable()
        payload = decode_tenant(job.researchbulkpayload, job.access.organization_id)
        ResearchReleasedSnapshot.objects.get_or_create(
            dataset=DATASET, defaults={"checksum": job.checksum}
        )
        audit(request.user, "interop.research_bulk_downloaded", job.pk, job.access.organization)
        response = HttpResponse(payload["ndjson"], content_type="application/fhir+ndjson")
        response["Cache-Control"] = "no-store"
        response["Content-Disposition"] = 'attachment; filename="MeasureReport.ndjson"'
        return response


@shared_task(ignore_result=True)
def reconcile_bulk():
    from identity.interop_policy import enabled

    if not enabled():
        return
    for key in (
        ResearchBulkJob.objects.filter(state="queued", expires_at__gt=timezone.now())
        .order_by("created_at")
        .values_list("pk", flat=True)[:20]
    ):
        prepare_bulk.delay(str(key))
