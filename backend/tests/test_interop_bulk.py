"""Bulk export tests use a declared synthetic archive boundary double."""

import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.db import DatabaseError, transaction
from django.utils import timezone
from test_identity import org_for, signed, user

from identity.interop_bulk import prepare_bulk, reconcile_bulk
from identity.models import Membership, ResearchAccessRequest, ResearchBulkJob, ResearchBulkPayload

pytestmark = pytest.mark.django_db


@pytest.fixture
def scenario(settings):
    settings.FHIR_INTEROP_ENABLED = True
    settings.RESEARCH_EXPORT_ENABLED = True
    settings.CLINICAL_MASTER_KEY = Fernet.generate_key().decode()
    actor = user("p5-research@patients.example", "organization_admin")
    org = org_for(actor)
    org.kind = "research"
    org.save(update_fields=["kind"])
    browser = signed(actor)
    actor.refresh_from_db()
    entry = ResearchAccessRequest.objects.create(
        organization=org,
        requested_by=actor,
        purpose="SYNTHETIC test aggregates",
        status="approved",
        checksum="a" * 64,
    )
    return actor, browser, entry


def test_research_bulk_is_async_bound_and_rechecks_archive_at_every_download(scenario):
    actor, browser, entry = scenario
    snapshot = ("a" * 64, [(2026, "2345-7", 10)])
    with (
        patch("identity.interop_bulk.current_snapshot", return_value=snapshot),
        patch("identity.interop_bulk.prepare_bulk.delay"),
    ):
        started = browser.client.get(
            f"/api/v1/fhir/$export?_type=MeasureReport&access_request={entry.pk}",
            HTTP_PREFER="respond-async",
        )
        assert started.status_code == 202, started.content
        path = started["Content-Location"]
        assert browser.client.get(path).status_code == 202
        job = ResearchBulkJob.objects.get()
        prepare_bulk(str(job.pk))
        ready = browser.client.get(path)
        assert ready.status_code == 200 and ready.data["requiresAccessToken"]
        file = path + "MeasureReport.ndjson"
        result = browser.client.get(file)
        assert result.status_code == 200 and result["Content-Type"] == "application/fhir+ndjson"
        resources = [json.loads(line) for line in result.content.splitlines()]
        assert resources[0]["resourceType"] == "MeasureReport" and resources[0]["type"] == "summary"
        assert b"Patient/" not in result.content and b"patient_id" not in result.content
        with pytest.raises(DatabaseError), transaction.atomic():
            ResearchBulkPayload.objects.all().delete()
        with patch("identity.interop_bulk.current_snapshot", return_value=("b" * 64, [])):
            assert browser.client.get(file).status_code == 409
        ResearchAccessRequest.objects.filter(pk=entry.pk).update(status="revoked")
        assert browser.client.get(file).status_code == 404


def test_bulk_role_expiry_and_reconciliation(scenario):
    actor, browser, entry = scenario
    job = ResearchBulkJob.objects.create(
        access=entry,
        requested_by=actor,
        auth_version=actor.auth_version,
        checksum=entry.checksum,
        expires_at=timezone.now() + timedelta(hours=1),
    )
    with patch("identity.interop_bulk.prepare_bulk.delay") as queue:
        reconcile_bulk()
        queue.assert_called_once_with(str(job.pk))
    Membership.objects.filter(user=actor).update(active=False)
    with patch("identity.interop_bulk.current_snapshot") as archive:
        prepare_bulk(str(job.pk))
        archive.assert_not_called()
    job.refresh_from_db()
    assert job.state == "cancelled" and not ResearchBulkPayload.objects.exists()
    assert browser.client.get(f"/api/v1/interop/research-exports/{job.pk}/").status_code == 404


def test_research_bulk_bearer_requires_mfa_approved_client_and_request(scenario, settings):
    from rest_framework.test import APIClient

    from identity.models import InteropApplication

    actor, _, entry = scenario
    settings.SMART_ISSUER = "https://issuer.example"
    InteropApplication.objects.create(
        organization=entry.organization, author=actor, client_id="SYNTHETIC-RESEARCH-CLIENT"
    )
    claims = {
        "active": True,
        "iss": settings.SMART_ISSUER,
        "aud": settings.PUBLIC_ORIGIN + "/api/v1/fhir",
        "sub": str(actor.pk),
        "tenant": str(entry.organization_id),
        "scope": "user/MeasureReport.rs",
        "client_id": "SYNTHETIC-RESEARCH-CLIENT",
        "research_access_request": str(entry.pk),
        "exp": (timezone.now() + timedelta(minutes=5)).timestamp(),
        "auth_time": timezone.now().timestamp(),
        "amr": ["mfa"],
        "auth_version": actor.auth_version,
    }
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer SYNTHETIC-RESEARCH-OPAQUE-TOKEN")
    with (
        patch("identity.interop_oauth.introspect", return_value=claims),
        patch(
            "identity.interop_bulk.current_snapshot",
            return_value=("a" * 64, [(2026, "2345-7", 10)]),
        ),
        patch("identity.interop_bulk.prepare_bulk.delay"),
    ):
        result = client.get(
            f"/api/v1/fhir/$export?_type=MeasureReport&access_request={entry.pk}",
            HTTP_PREFER="respond-async",
        )
        assert result.status_code == 202, result.content
        job = ResearchBulkJob.objects.get()
        prepare_bulk(str(job.pk))
        assert client.get(result["Content-Location"] + "MeasureReport.ndjson").status_code == 200
        with patch(
            "identity.interop_oauth.introspect", return_value={**claims, "amr": ["password"]}
        ):
            assert client.get(result["Content-Location"]).status_code == 401
        with patch(
            "identity.interop_oauth.introspect",
            return_value={**claims, "client_id": "NOT-APPROVED"},
        ):
            assert client.get(result["Content-Location"]).status_code == 401
