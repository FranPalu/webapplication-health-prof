import os

import psycopg
from django.conf import settings
from django.db import connection, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.response import Response

from identity.models import Membership, ResearchAccessRequest, ResearchReleasedSnapshot
from identity.research import MIN_PATIENTS, eligible_cells
from identity.research_archive import DATASET, read_snapshot, snapshot_digest
from identity.research_exports import encode_export
from identity.security import PlatformAdmin, audit, rate_limit
from identity.views import InputView


class ReleaseUnavailable(APIException):
    status_code = 409
    default_detail = "Research release unavailable or no longer current."


class AccessInput(serializers.Serializer):
    purpose = serializers.CharField(max_length=500)


class AccessOutput(serializers.ModelSerializer):
    class Meta:
        model = ResearchAccessRequest
        fields = ("id", "organization", "purpose", "status", "checksum", "created_at")


class AccessDecision(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["approve", "reject", "revoke"])


class ResearchExportInput(serializers.Serializer):
    format_name = serializers.ChoiceField(choices=["csv", "parquet", "fhir", "dashboard"])


def research_admins(request):
    if request.session.get("mfa_version") != request.user.auth_version:
        raise PermissionDenied()
    return Membership.objects.filter(
        user=request.user,
        role="admin",
        active=True,
        organization__kind="research",
    )


def current_snapshot():
    dsn = os.environ.get("RESEARCH_READ_DSN")
    if not settings.RESEARCH_EXPORT_ENABLED or not dsn:
        raise ReleaseUnavailable()
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", (741309621,))
    try:
        digest, rows = read_snapshot(dsn)
    except (psycopg.Error, ValueError) as exc:
        raise ReleaseUnavailable() from exc
    if not rows or digest != snapshot_digest(
        list(eligible_cells().values_list("year", "code", "patients"))
    ):
        raise ReleaseUnavailable()
    released = ResearchReleasedSnapshot.objects.filter(pk=DATASET).first()
    if released and digest != released.checksum:
        raise ReleaseUnavailable()
    return digest, rows


class ResearchCatalogView(InputView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(
            {
                "dataset": DATASET,
                "minimum_accounts": MIN_PATIENTS,
                "fields": {
                    "year": "Calendar year",
                    "code": "Approved LOINC code",
                    "accounts": "Distinct consenting accounts",
                },
                "formats": ["csv", "parquet", "fhir"],
            }
        )


class ResearchAccessView(InputView):
    serializer_class = AccessInput

    @extend_schema(responses=AccessOutput(many=True))
    def get(self, request, org_id):
        org = get_object_or_404(research_admins(request), organization_id=org_id)
        rows = ResearchAccessRequest.objects.filter(organization=org.organization).order_by(
            "-created_at", "-pk"
        )
        return self.get_paginated_response(
            AccessOutput(self.paginate_queryset(rows), many=True).data
        )

    @extend_schema(responses={201: AccessOutput})
    @transaction.atomic
    def post(self, request, org_id):
        rate_limit(request, "research-request", limit=12)
        member = get_object_or_404(research_admins(request), organization_id=org_id)
        entry = ResearchAccessRequest.objects.create(
            organization=member.organization, requested_by=request.user, **self.data(request)
        )
        audit(request.user, "research.access_requested", entry.pk, entry.organization)
        return Response(AccessOutput(entry).data, status=201)


class ResearchReviewListView(InputView):
    permission_classes = [PlatformAdmin]
    serializer_class = AccessOutput

    @extend_schema(responses=AccessOutput(many=True))
    def get(self, request):
        rows = ResearchAccessRequest.objects.order_by("-created_at", "-pk")
        return self.get_paginated_response(
            AccessOutput(self.paginate_queryset(rows), many=True).data
        )


class ResearchReviewView(InputView):
    permission_classes = [PlatformAdmin]
    serializer_class = AccessDecision

    @extend_schema(responses=AccessOutput)
    @transaction.atomic
    def post(self, request, request_id):
        if request.session.get("mfa_version") != request.user.auth_version:
            raise PermissionDenied()
        entry = get_object_or_404(ResearchAccessRequest.objects.select_for_update(), pk=request_id)
        decision = self.data(request)["decision"]
        if entry.requested_by_id == request.user.pk:
            raise PermissionDenied()
        if decision == "approve" and entry.status == "pending":
            entry.checksum, _ = current_snapshot()
            entry.status = "approved"
        elif decision == "reject" and entry.status == "pending":
            entry.status = "rejected"
        elif decision == "revoke" and entry.status == "approved":
            entry.status = "revoked"
        else:
            return Response({"code": "invalid_transition"}, status=409)
        entry.decided_by = request.user
        entry.save(update_fields=["status", "checksum", "decided_by"])
        audit(request.user, "research.access_" + entry.status, entry.pk, entry.organization)
        return Response(AccessOutput(entry).data)


class ResearchExportView(InputView):
    serializer_class = ResearchExportInput

    @extend_schema(
        responses={
            (200, "text/csv"): OpenApiTypes.BINARY,
            (200, "application/vnd.apache.parquet"): OpenApiTypes.BINARY,
            (200, "application/fhir+json"): OpenApiTypes.OBJECT,
            (200, "application/json"): OpenApiTypes.OBJECT,
        }
    )
    @transaction.atomic
    def post(self, request, request_id):
        rate_limit(request, "research-export", limit=12)
        entry = get_object_or_404(
            ResearchAccessRequest.objects.select_for_update().filter(
                organization_id__in=research_admins(request).values("organization_id"),
                status="approved",
            ),
            pk=request_id,
        )
        digest, rows = current_snapshot()
        if entry.checksum != digest:
            raise ReleaseUnavailable()
        format_name = self.data(request)["format_name"]
        ResearchReleasedSnapshot.objects.get_or_create(
            dataset=DATASET, defaults={"checksum": digest}
        )
        audit(request.user, "research.exported", entry.pk, entry.organization)
        if format_name == "dashboard":
            return Response(
                {
                    "dataset": DATASET,
                    "cells": [
                        {"year": year, "code": code, "accounts": accounts}
                        for year, code, accounts in rows
                    ],
                }
            )
        output, media_type, extension = encode_export(rows, format_name)
        response = HttpResponse(output, content_type=media_type)
        response["Content-Disposition"] = f'attachment; filename="{DATASET}.{extension}"'
        response["Cache-Control"] = "no-store"
        return response
