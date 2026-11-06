from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import DatabaseError, transaction
from django.utils import timezone
from test_identity import approve, org_for, patient, signed, user

from identity.clinical_safety import Limits, escalate_due, evaluate, matching_rule
from identity.models import (
    AuditEvent,
    CareRelationship,
    InAppNotification,
    LabAlertRule,
    LabResultReview,
    Membership,
)

VALUES = (-2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8)
PROFILES = (
    ("two-sided", Limits("mg/dL", Decimal(1), Decimal(6)), {-2, -1, 0, 1, 6, 7, 8}),
    ("low-only", Limits("mg/dL", Decimal(1), None), {-2, -1, 0, 1}),
    ("high-only", Limits("mg/dL", None, Decimal(6)), {6, 7, 8}),
    ("no-approved-rule", None, set()),
)


@pytest.mark.parametrize("value", VALUES)
@pytest.mark.parametrize("unit", ("mg/dL", "mmol/L", ""))
@pytest.mark.parametrize("name,limits,critical", PROFILES, ids=[row[0] for row in PROFILES])
def test_synthetic_limit_scenarios(value, unit, name, limits, critical):
    expected = (
        "insufficient"
        if not limits or unit != "mg/dL"
        else ("critical" if value in critical else "within_limits")
    )
    assert evaluate(Decimal(value), unit, limits) == expected, name


def test_incomplete_or_overlapping_context_fails_closed():
    baseline = dict(code="2345-7", laboratory="Synthetic lab", min_age=18, max_age=65)
    general = SimpleNamespace(**baseline, sex="")
    specific = SimpleNamespace(**baseline, sex="female")
    observation = SimpleNamespace(code="2345-7", reference_range={"laboratory": "Synthetic lab"})
    assert matching_rule([general, specific], observation, 30, "") is None
    assert matching_rule([general, specific], observation, 30, "female") is None
    assert matching_rule([general, specific], observation, 30, "male") is general
    assert matching_rule([specific], observation, 65, "female") is specific
    assert matching_rule([specific], observation, 66, "female") is None
    assert evaluate(Decimal("NaN"), "mg/dL", Limits("mg/dL", None, Decimal(6))) == "insufficient"


@pytest.mark.django_db
def test_rule_approval_result_queue_escalation_and_acknowledgment(
    settings, django_capture_on_commit_callbacks, mailoutbox
):
    settings.CLINICAL_SAFETY_ENABLED = True
    author, reviewer, outsider = [
        user(f"lab-safety-{i}@patients.example", "professional") for i in range(3)
    ]
    for clinician in (author, reviewer, outsider):
        approve(clinician)
    org = org_for(author)
    Membership.objects.create(organization=org, user=reviewer, role="admin")
    record = patient(org, author)
    CareRelationship.objects.create(patient=record, professional=reviewer)
    proposing, reviewing, outside = (
        signed(clinician) for clinician in (author, reviewer, outsider)
    )
    rule_route = f"organizations/{org.pk}/lab-rules/"
    rule = {
        "code": "2345-7",
        "unit": "mg/dL",
        "laboratory": "Synthetic lab",
        "min_age": 18,
        "max_age": 80,
        "low": "1",
        "high": "6",
        "sla_minutes": 2,
        "backup": str(reviewer.pk),
        "evidence": "Synthetic QA limits only",
    }
    assert outside.post(rule_route, rule).status_code == 403
    assert proposing.post(rule_route, {**rule, "unit": "mmol/L"}).status_code == 400
    response = proposing.post(rule_route, rule)
    assert response.status_code == 201 and response.data["approved"] is False
    approval = rule_route + f"{response.data['id']}/approve/"
    assert proposing.post(approval, {}).status_code == 403
    proof = {
        "identifier_kind": "facility",
        "identifier_value": "SYN-SAFETY",
        "source_birth_date": str(record.birth_date),
    }
    assert proposing.post(f"clinical/patients/{record.pk}/identifiers/", proof).status_code == 201
    intake = f"clinical/patients/{record.pk}/reports/"
    payload = {
        **proof,
        "code": "11502-2",
        "title": "Synthetic",
        "effective_at": "2026-01-02T12:00:00Z",
        "observations": [
            {
                "code": "2345-7",
                "display": "Synthetic",
                "value": "6",
                "unit": "mg/dL",
                "reference_range": {"laboratory": "Synthetic lab", "low": "0"},
            }
        ],
    }
    assert proposing.post(intake, payload).status_code == 201
    assert LabResultReview.objects.get().outcome == "insufficient"
    assert reviewing.post(approval, {}).data["approved"] is True
    with django_capture_on_commit_callbacks(execute=True):
        assert proposing.post(intake, payload).status_code == 201
    assert mailoutbox[-1].to == [author.email]
    assert str(record.pk) not in mailoutbox[-1].body
    result = LabResultReview.objects.get(outcome="critical")
    assert result.findings[0]["rule"] == str(response.data["id"])
    assert (
        InAppNotification.objects.filter(user=author, category="clinical.result_attention").count()
        == 1
    )
    queue = f"clinical/patients/{record.pk}/result-reviews/"
    ack = f"clinical/result-reviews/{result.pk}/acknowledge/"
    assert proposing.get(queue).data["count"] == 2
    assert outside.get(queue).status_code == 404
    assert outside.post(ack, {}).status_code == 404
    assert escalate_due(timezone.now()) == 0
    with django_capture_on_commit_callbacks(execute=True):
        assert escalate_due(result.due_at) == 1
    assert mailoutbox[-1].to == [reviewer.email]
    assert escalate_due(result.due_at) == 0
    assert (
        InAppNotification.objects.filter(
            user=reviewer, category="clinical.result_escalated"
        ).count()
        == 1
    )
    assert reviewing.post(ack, {"patient": str(org.pk)}).status_code == 400
    confirmation = {"patient": str(record.pk)}
    assert reviewing.post(ack, confirmation).data["escalation_assigned"] is True
    assert reviewing.post(ack, confirmation).status_code == 200
    assert proposing.get(queue).data["count"] == 2
    complete = f"clinical/result-reviews/{result.pk}/complete/"
    assert (
        reviewing.post(complete, {**confirmation, "note": "Synthetic source checked"}).status_code
        == 200
    )
    assert proposing.get(queue).data["count"] == 1
    assert AuditEvent.objects.filter(action="clinical.result_acknowledged").count() == 1

    assert proposing.post(intake, payload).status_code == 201
    unassigned = LabResultReview.objects.get(outcome="critical", acknowledged_at__isnull=True)
    CareRelationship.objects.filter(patient=record, professional=reviewer).update(active=False)
    assert escalate_due(unassigned.due_at) == 1
    unassigned.refresh_from_db()
    assert unassigned.escalation_assigned is False
    assert (
        InAppNotification.objects.filter(
            user=reviewer, category="clinical.result_escalated"
        ).count()
        == 1
    )
    assert proposing.get(queue).data["count"] == 2

    retired = proposing.post(rule_route, {**rule, "enabled": False})
    assert retired.data["version"] == 2
    assert reviewing.post(rule_route + f"{retired.data['id']}/approve/", {}).status_code == 200
    assert proposing.post(intake, payload).status_code == 201
    assert LabResultReview.objects.filter(outcome="insufficient").count() == 2
    with pytest.raises(DatabaseError), transaction.atomic():
        LabAlertRule.objects.all().update(evidence="changed")
    settings.CLINICAL_SAFETY_ENABLED = False
    assert proposing.get(queue).status_code == 404
