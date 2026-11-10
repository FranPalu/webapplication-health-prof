"""Synthetic P5 FHIR resources; external identity verification is mocked explicitly."""

import copy
import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import DatabaseError, transaction
from django.utils import timezone
from rest_framework.test import APIClient
from test_identity import approve, org_for, patient, signed, user

from identity.fhir_gateway import CONFIRMATION_URL, CORRECTION_URL
from identity.models import (
    AuditEvent,
    ClinicalReport,
    InteropApplication,
    InteropGrant,
    InteropGrantRevocation,
    PatientIdentifier,
)
from identity.patient_identification import identifier_digest

pytestmark = pytest.mark.django_db


@pytest.fixture
def scenario(settings):
    settings.FHIR_INTEROP_ENABLED = True
    author = user("p5-author@patients.example", "professional")
    approve(author)
    account = user("p5-patient@patients.example")
    record = patient(org_for(author), author)
    record.account = account
    record.save(update_fields=["account"])
    PatientIdentifier.objects.create(
        patient=record,
        organization=record.organization,
        kind="facility",
        digest=identifier_digest(record.organization_id, "facility", "SYNTHETIC-P5"),
        recorded_by=author,
    )
    return author, account, record


def payload(record):
    return {
        "resourceType": "DiagnosticReport",
        "status": "preliminary",
        "code": {
            "coding": [
                {"system": "http://loinc.org", "code": "11502-2", "display": "Synthetic lab"}
            ]
        },
        "subject": {"reference": f"Patient/{record.pk}"},
        "effectiveDateTime": (timezone.now() - timedelta(minutes=1)).isoformat(),
        "extension": [
            {
                "url": CONFIRMATION_URL,
                "extension": [
                    {"url": "identifier_kind", "valueString": "facility"},
                    {"url": "identifier_value", "valueString": "SYNTHETIC-P5"},
                    {"url": "source_birth_date", "valueString": str(record.birth_date)},
                ],
            }
        ],
        "contained": [
            {
                "resourceType": "Observation",
                "id": "glucose",
                "status": "preliminary",
                "code": {
                    "coding": [
                        {
                            "system": "http://loinc.org",
                            "code": "2345-7",
                            "display": "Synthetic glucose",
                        }
                    ]
                },
                "valueQuantity": {
                    "value": 85,
                    "system": "http://unitsofmeasure.org",
                    "code": "mg/dL",
                    "unit": "mg/dL",
                },
            }
        ],
        "result": [{"reference": "#glucose"}],
    }


def test_standard_fhir_create_search_update_and_no_patient_preliminary(scenario):
    author, account, record = scenario
    browser = signed(author)
    path = "fhir/DiagnosticReport"
    response = browser.post(path, payload(record))
    assert response.status_code == 201, response.content
    data = response.json()
    root = data["id"]
    assert response["ETag"] == 'W/"1"' and response["Location"].endswith(f"/{root}/_history/1")
    assert data["status"] == "preliminary"
    search = browser.get(path + "?patient=" + str(record.pk) + "&code=http://loinc.org|11502-2")
    assert search.status_code == 200, search.content
    assert search.json()["total"] == 1 and search.json()["entry"][0]["resource"]["id"] == root
    assert signed(account).get(path).json()["total"] == 0
    correction = payload(record)
    correction["extension"].append({"url": CORRECTION_URL, "valueString": "Synthetic correction"})
    correction["contained"][0]["valueQuantity"]["value"] = 90
    url = "/api/v1/fhir/DiagnosticReport/" + root
    client = browser.client
    csrf = client.cookies["csrftoken"].value
    assert client.put(url, correction, format="json", HTTP_X_CSRFTOKEN=csrf).status_code == 412
    updated = client.put(
        url, correction, format="json", HTTP_X_CSRFTOKEN=csrf, HTTP_IF_MATCH='W/"1"'
    )
    assert updated.status_code == 200, updated.content
    assert updated.json()["meta"]["versionId"] == "2"
    assert (
        client.put(
            url, correction, format="json", HTTP_X_CSRFTOKEN=csrf, HTTP_IF_MATCH='W/"1"'
        ).status_code
        == 412
    )
    assert browser.get(path + "/" + root + "/_history/1").json()["meta"]["versionId"] == "1"
    assert browser.get(path + "?patient=" + str(record.pk)).json()["total"] == 1
    assert ClinicalReport.objects.count() == 2
    assert AuditEvent.objects.filter(action="interop.fhir_searched", actor=author).exists()


@pytest.mark.parametrize(
    "change",
    ["status", "unit", "subject", "identifier", "contained", "extra", "duplicate", "unknown_ref"],
)
def test_fhir_intake_rejects_unsafe_or_silently_lost_fields(scenario, change):
    author, _, record = scenario
    data = payload(record)
    if change == "status":
        data["status"] = "final"
    if change == "unit":
        data["contained"][0]["valueQuantity"]["code"] = "mmol/L"
    if change == "subject":
        data["subject"]["reference"] = "https://other.example/Patient/1"
    if change == "identifier":
        data["extension"][0]["extension"][1]["valueString"] = "WRONG"
    if change == "contained":
        data["contained"] = []
    if change == "extra":
        data["conclusion"] = "Must not be silently ignored"
    if change == "duplicate":
        data["contained"].append(copy.deepcopy(data["contained"][0]))
        data["result"].append({"reference": "#glucose"})
    if change == "unknown_ref":
        data["result"][0]["reference"] = "#missing"
    response = signed(author).post("fhir/DiagnosticReport", data)
    assert response.status_code == 400, response.content
    assert response.json()["resourceType"] == "OperationOutcome"
    assert not ClinicalReport.objects.exists()


@pytest.mark.parametrize(
    "query",
    [
        "_include=Patient",
        "patient=invalid",
        "_count=0",
        "_count=101",
        "_offset=-1",
        "_count=x",
        "_id=invalid",
        "_count=2&_count=3",
    ],
)
def test_search_rejects_unsupported_and_ambiguous_parameters(scenario, query):
    author, _, _ = scenario
    response = signed(author).get("fhir/DiagnosticReport?" + query)
    assert response.status_code == 400


@pytest.mark.parametrize(
    "kind",
    [
        "Patient",
        "Organization",
        "Practitioner",
        "Consent",
        "DocumentReference",
        "Encounter",
        "DiagnosticReport",
        "Observation",
        "Provenance",
    ],
)
def test_search_only_exposes_current_authorized_scope(scenario, kind):
    author, _, record = scenario
    outsider = user("p5-other@patients.example", "professional")
    approve(outsider)
    browser = signed(author)
    result = browser.get("fhir/" + kind)
    assert result.status_code == 200, result.content
    assert result.json()["resourceType"] == "Bundle"
    if kind == "Patient":
        assert result.json()["entry"][0]["resource"]["id"] == str(record.pk)
        assert signed(outsider).get("fhir/Patient?_id=" + str(record.pk)).json()["total"] == 0


def grant(scenario):
    author, account, record = scenario
    app = InteropApplication.objects.create(
        organization=record.organization, author=author, client_id="synthetic-app"
    )
    result = signed(account).post(
        f"clinical/patients/{record.pk}/interop/grants/",
        {
            "application": str(app.pk),
            "scopes": ["patient/Patient.rs"],
            "expires_at": (timezone.now() + timedelta(days=1)).isoformat(),
            "consent_version": 1,
            "confirmed": True,
        },
    )
    assert result.status_code == 201, result.content
    return InteropGrant.objects.get(pk=result.data["id"])


def token_claims(entry):
    from django.conf import settings

    return {
        "active": True,
        "iss": settings.SMART_ISSUER,
        "aud": settings.PUBLIC_ORIGIN + "/api/v1/fhir",
        "sub": str(entry.grantor_id),
        "grant_id": str(entry.pk),
        "patient": str(entry.patient_id),
        "tenant": str(entry.patient.organization_id),
        "client_id": entry.application.client_id,
        "exp": (timezone.now() + timedelta(minutes=5)).timestamp(),
        "scope": "patient/Patient.rs",
        "auth_version": entry.grantor.auth_version,
    }


def test_smart_scope_compartment_revocation_and_no_session_fallback(scenario, settings):
    settings.SMART_ISSUER = "https://issuer.example"
    entry = grant(scenario)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer SYNTHETIC-OPAQUE-ACCESS-TOKEN")
    with patch("identity.interop_oauth.introspect", return_value=token_claims(entry)):
        response = client.get(f"/api/v1/fhir/Patient/{entry.patient_id}")
        assert response.status_code == 200, response.content
        assert client.get("/api/v1/fhir/Patient").json()["total"] == 1
        assert client.get("/api/v1/fhir/Observation").status_code == 403
        assert client.post("/api/v1/fhir/DiagnosticReport", {}, format="json").status_code == 403
        signed(entry.grantor).post(
            f"interop/grants/{entry.pk}/revoke/", {"reason": "Synthetic revocation"}
        )
        assert client.get(f"/api/v1/fhir/Patient/{entry.patient_id}").status_code == 401
    with pytest.raises(DatabaseError), transaction.atomic():
        InteropGrantRevocation.objects.all().delete()


@pytest.mark.parametrize(
    "field,value",
    [
        ("active", False),
        ("iss", "https://other.example"),
        ("aud", "wrong"),
        ("exp", 0),
        ("exp", True),
        ("sub", "invalid"),
        ("tenant", "invalid"),
        ("patient", "wrong"),
        ("auth_version", 999),
        ("scope", "patient/*.rs"),
        ("token_type", 123),
    ],
)
def test_invalid_introspection_never_discloses_data(scenario, settings, field, value):
    settings.SMART_ISSUER = "https://issuer.example"
    entry = grant(scenario)
    claims = {**token_claims(entry), field: value}
    client = APIClient()
    with patch("identity.interop_oauth.introspect", return_value=claims):
        response = client.get(
            f"/api/v1/fhir/Patient/{entry.patient_id}",
            HTTP_AUTHORIZATION="Bearer SYNTHETIC-OPAQUE-ACCESS-TOKEN",
        )
    assert response.status_code == 401, response.content


def test_disabled_interop_and_bearer_do_not_bypass_legacy_authentication(scenario, settings):
    author, _, record = scenario
    settings.FHIR_INTEROP_ENABLED = False
    browser = signed(author)
    assert browser.get(f"fhir/Patient/{record.pk}").status_code == 200
    assert browser.get("fhir/Patient").status_code == 403
    assert browser.get("fhir/.well-known/smart-configuration").status_code == 503
    client = APIClient()
    assert (
        client.get(
            f"/api/v1/fhir/Patient/{record.pk}",
            HTTP_AUTHORIZATION="Bearer SYNTHETIC-OPAQUE-ACCESS-TOKEN",
        ).status_code
        == 401
    )


def test_emit_actual_synthetic_fhir_resources_for_hl7_validator(scenario, settings):
    import os
    from pathlib import Path
    from uuid import uuid4

    from cryptography.fernet import Fernet
    from test_clinical import PDF

    from identity.clinical import seal
    from identity.interop_oauth import fhir_base
    from identity.models import (
        ClinicalDocument,
        ClinicalDocumentVersion,
        ClinicalEncounter,
        ConsentTextVersion,
        PatientConsent,
    )

    settings.CLINICAL_MASTER_KEY = Fernet.generate_key().decode()
    settings.CLINICAL_SAFETY_ENABLED = True
    author, account, record = scenario
    browser = signed(author)
    report = browser.post("fhir/DiagnosticReport", payload(record)).json()
    encounter = ClinicalEncounter.objects.create(
        patient=record,
        author=author,
        started_at=timezone.now() - timedelta(hours=1),
        ended_at=timezone.now(),
    )
    document = ClinicalDocument.objects.create(patient=record, author=author, kind="report")
    version = ClinicalDocumentVersion.objects.create(
        document=document,
        number=1,
        title="Synthetic document",
        media_type="application/pdf",
        size=len(PDF),
        **seal(PDF, record.organization_id),
    )
    text = ConsentTextVersion.objects.create(
        purpose="care",
        version=987,
        locale="it",
        text="SYNTHETIC validation fixture",
        content_hash="a" * 64,
    )
    consent = PatientConsent.objects.create(
        patient=record, actor=account, text_version=text, decision="granted"
    )
    references = [
        f"Patient/{record.pk}",
        f"Organization/{record.organization_id}",
        f"Practitioner/{author.pk}",
        f"Encounter/{encounter.pk}",
        f"DocumentReference/{version.pk}",
        f"Binary/{version.pk}",
        f"DiagnosticReport/{report['id']}",
        report["result"][0]["reference"],
        f"Provenance/{report['id']}-v1",
    ]
    from identity.models import LabOrder

    order = LabOrder.objects.create(
        patient=record, author=author, code="2345-7", due_at=timezone.now() + timedelta(hours=1)
    )
    references.append(f"ServiceRequest/{order.pk}")
    resources = [browser.get("fhir/" + reference).json() for reference in references]
    resources.append(signed(account).get(f"fhir/Consent/{consent.pk}").json())
    resources += [browser.get("fhir/metadata").json(), browser.get("fhir/Patient?_count=1").json()]
    assert all(resource.get("resourceType") != "OperationOutcome" for resource in resources)
    from identity.research_exports import encode_export

    aggregate, _, _ = encode_export([(2026, "2345-7", 10)], "fhir")
    resources.append(json.loads(aggregate)["entry"][0]["resource"])
    target = os.environ.get("FHIR_VALIDATION_OUTPUT")
    if target:
        directory = Path(target)
        directory.mkdir(parents=True, exist_ok=True)
        collection = {
            "resourceType": "Bundle",
            "id": "claria-p5-validation",
            "type": "collection",
            "entry": [
                {
                    "fullUrl": (
                        fhir_base() + "/" + resource["resourceType"] + "/" + resource["id"]
                        if "id" in resource
                        else "urn:uuid:" + str(uuid4())
                    ),
                    "resource": resource,
                }
                for resource in resources
            ],
        }
        (directory / "claria-p5-validation.json").write_text(
            json.dumps(collection, ensure_ascii=False, indent=2)
        )


def test_application_registration_and_revocation_require_tenant_admin_and_patient_owner(scenario):
    from identity.models import Membership

    author, account, record = scenario
    browser = signed(author)
    path = f"organizations/{record.organization_id}/interop/applications/"
    registered = browser.post(path, {"client_id": "SYNTHETIC-APP-API"})
    assert registered.status_code == 201, registered.content
    application = registered.data["id"]
    assert browser.post(path, {"client_id": "SYNTHETIC-APP-API"}).data["id"] == application
    patient_browser = signed(account)
    assert patient_browser.post(path, {"client_id": "SYNTHETIC-PATIENT-APP"}).status_code == 403
    fields = {
        "application": str(application),
        "scopes": ["patient/Patient.rs"],
        "expires_at": (timezone.now() + timedelta(days=1)).isoformat(),
        "consent_version": 1,
        "confirmed": True,
    }
    endpoint = f"clinical/patients/{record.pk}/interop/grants/"
    grant = patient_browser.post(endpoint, fields)
    assert grant.status_code == 201, grant.content
    assert patient_browser.post(endpoint, {**fields, "confirmed": False}).status_code == 400
    assert patient_browser.post(endpoint, {**fields, "scopes": ["patient/*.rs"]}).status_code == 400
    assert (
        patient_browser.post(
            endpoint, {**fields, "expires_at": (timezone.now() + timedelta(days=91)).isoformat()}
        ).status_code
        == 400
    )
    assert (
        browser.post(
            f"organizations/{record.organization_id}/interop/applications/{application}/revoke/",
            {"reason": "SYNTHETIC suspension"},
        ).status_code
        == 204
    )
    assert patient_browser.post(endpoint, fields).status_code == 404
    Membership.objects.filter(user=author, organization=record.organization).update(
        role="professional"
    )
    assert browser.post(path, {"client_id": "SYNTHETIC-NONADMIN"}).status_code == 404


def test_introspection_uses_bound_tls_transport_and_rejects_redirectable_or_invalid_payloads(
    settings,
):
    from identity.interop_oauth import IntegrationUnavailable, introspect

    settings.SMART_INTROSPECTION_URL = "https://issuer.example/introspection"
    settings.SMART_CLIENT_ID = "SYNTHETIC-RESOURCE-SERVER"
    settings.SMART_CLIENT_SECRET = "SYNTHETIC-TEST-ONLY-NOT-A-CREDENTIAL"
    with patch("identity.interop_oauth.build_opener") as build:
        build.return_value.open.return_value.__enter__.return_value.read.return_value = (
            b'{"active":false}'
        )
        assert introspect("SYNTHETIC-TOKEN") == {"active": False}
        call = build.return_value.open.call_args
        assert call.args[0].full_url == settings.SMART_INTROSPECTION_URL
        assert call.args[0].get_method() == "POST" and call.kwargs["timeout"] == 5
        for body in (b"[]", b"invalid", b"x" * 65537):
            build.return_value.open.return_value.__enter__.return_value.read.return_value = body
            with pytest.raises(IntegrationUnavailable):
                introspect("SYNTHETIC-TOKEN")
    settings.SMART_INTROSPECTION_URL = "http://untrusted.example/"
    with pytest.raises(IntegrationUnavailable):
        introspect("SYNTHETIC-TOKEN")


def test_fhir_methods_not_advertised_are_rejected_without_mutation(scenario):
    author, _, record = scenario
    browser = signed(author)
    assert browser.post("fhir/Patient", {}).status_code == 405
    assert browser.post(f"fhir/Patient/{record.pk}", {}).status_code == 405
    csrf = browser.client.cookies["csrftoken"].value
    assert (
        browser.client.put(
            "/api/v1/fhir/DiagnosticReport", {}, format="json", HTTP_X_CSRFTOKEN=csrf
        ).status_code
        == 405
    )
    assert browser.get("fhir/metadata").json()["rest"][0]["resource"]
    assert not ClinicalReport.objects.exists()


def test_oauth_document_content_requires_its_granted_security_context(scenario, settings):
    import base64

    from cryptography.fernet import Fernet
    from test_clinical import PDF

    from identity.clinical import seal
    from identity.models import ClinicalDocument, ClinicalDocumentVersion

    settings.SMART_ISSUER = "https://issuer.example"
    settings.CLINICAL_MASTER_KEY = Fernet.generate_key().decode()
    author, _, record = scenario
    initial = grant(scenario)
    entry = InteropGrant.objects.create(
        application=initial.application,
        patient=initial.patient,
        grantor=initial.grantor,
        scopes=["patient/DocumentReference.rs"],
        expires_at=initial.expires_at,
        consent_version=1,
    )
    document = ClinicalDocument.objects.create(patient=record, author=author, kind="report")
    version = ClinicalDocumentVersion.objects.create(
        document=document,
        number=1,
        title="Synthetic PDF",
        media_type="application/pdf",
        size=len(PDF),
        **seal(PDF, record.organization_id),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer SYNTHETIC-OPAQUE-ACCESS-TOKEN")
    with patch(
        "identity.interop_oauth.introspect",
        return_value={**token_claims(entry), "scope": "patient/DocumentReference.rs"},
    ):
        resource = client.get(f"/api/v1/fhir/DocumentReference/{version.pk}")
        assert resource.status_code == 200, resource.content
        assert resource.json()["content"][0]["attachment"]["url"].endswith(
            f"/fhir/Binary/{version.pk}"
        )
        binary = client.get(f"/api/v1/fhir/Binary/{version.pk}")
        assert binary.status_code == 200 and base64.b64decode(binary.json()["data"]) == PDF
    with patch("identity.interop_oauth.introspect", return_value=token_claims(initial)):
        assert client.get(f"/api/v1/fhir/Binary/{version.pk}").status_code == 403
    assert AuditEvent.objects.filter(
        action="interop.fhir_binary_read", actor=entry.grantor
    ).exists()


def test_minor_intake_and_self_grant_require_unimplemented_guardian_workflow(scenario):
    author, account, record = scenario
    record.birth_date = timezone.localdate()
    record.save(update_fields=["birth_date"])
    assert signed(author).post("fhir/DiagnosticReport", payload(record)).status_code == 404
    app = InteropApplication.objects.create(
        organization=record.organization, author=author, client_id="SYNTHETIC-MINOR-CASE"
    )
    result = signed(account).post(
        f"clinical/patients/{record.pk}/interop/grants/",
        {
            "application": str(app.pk),
            "scopes": ["patient/Patient.r"],
            "expires_at": (timezone.now() + timedelta(days=1)).isoformat(),
            "consent_version": 1,
            "confirmed": True,
        },
    )
    assert result.status_code == 404 and not ClinicalReport.objects.exists()
