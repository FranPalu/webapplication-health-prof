from datetime import timedelta

import pytest
from django.utils import timezone
from test_identity import approve, org_for, patient, signed, user

from identity.models import LabOrderResult, LabResultReview


@pytest.mark.django_db
def test_order_remains_pending_until_latest_result_is_reviewed(settings):
    settings.CLINICAL_SAFETY_ENABLED = True
    clinician = user("lab-order@patients.example", "professional")
    approve(clinician)
    browser = signed(clinician)
    org = org_for(clinician)
    record, other = (patient(org, clinician) for _ in range(2))
    proof = {
        "identifier_kind": "facility",
        "identifier_value": "SYN-LAB-ORDER",
        "source_birth_date": str(record.birth_date),
    }

    def path(subject, endpoint):
        return f"clinical/patients/{subject.pk}/{endpoint}/"

    assert browser.post(path(record, "identifiers"), proof).status_code == 201
    other_proof = {**proof, "identifier_value": "SYN-LAB-OTHER"}
    assert browser.post(path(other, "identifiers"), other_proof).status_code == 201
    orders = path(record, "lab-orders")
    creation = browser.post(
        orders,
        {
            **proof,
            "code": "2345-7",
            "due_at": (timezone.now() + timedelta(days=1)).isoformat(),
        },
    )
    assert creation.status_code == 201, creation.content
    assert browser.get(orders).data["results"][0]["status"] == "awaiting_result"
    order_id = str(creation.data["id"])
    fhir = f"fhir/ServiceRequest/{order_id}"
    assert browser.get(fhir).json()["status"] == "active"
    assert (
        browser.get("fhir/metadata").json()["rest"][0]["resource"][-1]["type"] == "ServiceRequest"
    )
    assert (
        browser.post(
            orders, {**proof, "code": "2345-7", "due_at": "2020-01-01T00:00:00Z"}
        ).status_code
        == 400
    )
    report = {
        **proof,
        "code": "11502-2",
        "title": "Synthetic source",
        "effective_at": timezone.now().isoformat(),
        "order_id": order_id,
        "observations": [{"code": "2345-7", "display": "Synthetic", "value": "6", "unit": "mg/dL"}],
    }
    assert browser.post(path(other, "reports"), {**report, **other_proof}).status_code == 404
    wrong_analyte = [{**report["observations"][0], "code": "14749-6", "unit": "mmol/L"}]
    assert (
        browser.post(path(record, "reports"), {**report, "observations": wrong_analyte}).status_code
        == 400
    )
    created = browser.post(path(record, "reports"), report)
    assert created.status_code == 201, created.content
    assert browser.get(f"fhir/DiagnosticReport/{created.data['id']}").json()["basedOn"] == [
        {"reference": f"ServiceRequest/{order_id}"}
    ]
    assert browser.post(path(record, "reports"), report).status_code == 400
    assert browser.get(orders).data["results"][0]["status"] == "awaiting_review"

    def complete(version):
        review = LabResultReview.objects.get(report__version=version)
        review_path = f"clinical/result-reviews/{review.pk}/"
        payload = {"patient": str(record.pk), "note": "Synthetic result verified"}
        assert browser.post(review_path + "complete/", payload).status_code == 400
        assert (
            browser.post(review_path + "acknowledge/", {"patient": str(record.pk)}).status_code
            == 200
        )
        assert browser.get(orders).data["count"] == 1
        assert browser.post(review_path + "complete/", payload).status_code == 200
        assert browser.get(orders).data["count"] == 0

    complete(1)
    assert browser.get(fhir).json()["status"] == "completed"
    correction = {key: value for key, value in report.items() if key != "order_id"}
    response = browser.post(
        f"clinical/reports/{created.data['id']}/corrections/",
        {**correction, "expected_version": 1, "correction_reason": "Synthetic correction"},
    )
    assert response.status_code == 201, response.content
    assert browser.get(fhir).json()["status"] == "active"
    assert LabOrderResult.objects.count() == 1
    assert browser.get(orders).data["results"][0]["status"] == "awaiting_review"
    complete(2)
