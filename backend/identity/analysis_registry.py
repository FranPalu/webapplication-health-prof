"""Versioned model-card manifest and append-only tenant execution policy."""

import hashlib
import json
from pathlib import Path

from django.db import transaction
from django.db.models import Exists, F, OuterRef
from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from identity.models import AnalysisJob, AnalysisPolicyEvent, Membership, Organization
from identity.security import audit
from identity.services import verified_professional
from identity.views import InputView

MANIFEST = Path(__file__).parent / "model_cards" / "registry.json"


def manifest():
    content = MANIFEST.read_bytes()
    cards = json.loads(content)
    implementation = hashlib.sha256(
        (MANIFEST.parent.parent / "analysis_pipeline.py").read_bytes()
    ).hexdigest()
    cards["components"][0]["checksum"] = implementation
    cards["prompt"]["implementation_sha256"] = implementation
    canonical = json.dumps(cards, ensure_ascii=False, sort_keys=True).encode()
    return cards, hashlib.sha256(canonical).hexdigest()


def current_policy(organization_id):
    event = (
        AnalysisPolicyEvent.objects.filter(organization_id=organization_id).order_by("-pk").first()
    )
    return event if event and event.enabled and event.manifest_hash == manifest()[1] else None


def current_policy_jobs():
    newer = AnalysisPolicyEvent.objects.filter(
        organization_id=OuterRef("version__document__patient__organization_id"),
        pk__gt=OuterRef("policy_id"),
    )
    return (
        AnalysisJob.objects.filter(
            policy__enabled=True,
            policy__manifest_hash=manifest()[1],
            policy__organization_id=F("version__document__patient__organization_id"),
        )
        .alias(policy_changed=Exists(newer))
        .filter(policy_changed=False)
    )


class AnalysisPolicyInput(serializers.Serializer):
    enabled = serializers.BooleanField()
    manifest_hash = serializers.RegexField(r"^[a-f0-9]{64}$")
    reason = serializers.CharField(max_length=500)


class AnalysisPolicyView(InputView):
    serializer_class = AnalysisPolicyInput

    def require_admin(self, request, org_id):
        if not verified_professional(request.user):
            raise PermissionDenied()
        get_object_or_404(
            Membership, user=request.user, organization_id=org_id, role="admin", active=True
        )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, org_id):
        self.require_admin(request, org_id)
        cards, digest = manifest()
        audit(request.user, "analysis.registry_read", org_id)
        active = current_policy(org_id)
        return Response({"manifest": cards, "manifest_hash": digest, "enabled": active is not None})

    @extend_schema(responses={201: OpenApiTypes.OBJECT})
    @transaction.atomic
    def post(self, request, org_id):
        self.require_admin(request, org_id)
        data = self.data(request)
        organization = get_object_or_404(Organization.objects.select_for_update(), pk=org_id)
        if data["manifest_hash"] != manifest()[1]:
            raise Http404
        event = AnalysisPolicyEvent.objects.create(
            organization=organization, author=request.user, **data
        )
        audit(
            request.user,
            "analysis.registry_enabled" if event.enabled else "analysis.registry_disabled",
            event.pk,
            organization,
        )
        return Response({"id": event.pk, "enabled": event.enabled}, status=201)
