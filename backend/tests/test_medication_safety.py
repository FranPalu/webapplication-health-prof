from decimal import Decimal
from unittest.mock import patch

import pytest
from django.db import DatabaseError, transaction
from test_identity import approve, org_for, patient, signed, user

from identity.medication_safety import (
    DrugFacts,
    Evidence,
    MedicationSnapshot,
    MedicationSourceUnavailable,
)
from identity.models import AuditEvent, MedicationSafetyOverride


class SyntheticProvider:
    def snapshot(self, *, medications, allergies, conditions):
        evidence = Evidence("Synthetic fixture — no clinical source", "synthetic")
        a, b = "SYN-DRUG-A", "SYN-DRUG-B"
        return MedicationSnapshot(
            "Synthetic fixture",
            "1",
            "Test fixture authored in this repository",
            evidence,
            True,
            {
                (a, "SYN-ROUTE"): DrugFacts(
                    frozenset({"SYN-ALLERGEN"}), frozenset({"SYN-GROUP"}), Decimal(4), "mg"
                ),
                (b, "SYN-ROUTE"): DrugFacts(
                    frozenset({"SYN-B"}), frozenset({"SYN-GROUP"}), Decimal(8), "mg"
                ),
            },
            {frozenset((a, b)): evidence},
            {(b, "SYN-CONDITION"): evidence},
        )


@pytest.mark.django_db
def test_synthetic_screening_requires_evidence_and_audits_motivated_override(settings):
    settings.CLINICAL_SAFETY_ENABLED = True
    settings.CLINICAL_MEDICATION_PROVIDER = ""
    clinician = user("medication-review@patients.example", "professional")
    outsider = user("medication-outside@patients.example", "professional")
    approve(clinician)
    approve(outsider)
    org = org_for(clinician)
    record = patient(org, clinician)
    browser, outside = signed(clinician), signed(outsider)
    proof = {
        "identifier_kind": "facility",
        "identifier_value": "SYN-MEDICAL",
        "source_birth_date": str(record.birth_date),
    }
    assert browser.post(f"clinical/patients/{record.pk}/identifiers/", proof).status_code == 201
    route = f"clinical/patients/{record.pk}/medication-checks/"
    payload = {
        **proof,
        "context_confirmed": True,
        "medications": [
            {"code": code, "route": "SYN-ROUTE", "unit": "mg", "daily_dose": "5"}
            for code in ("SYN-DRUG-A", "SYN-DRUG-B")
        ],
        "allergies": ["SYN-ALLERGEN"],
        "conditions": ["SYN-CONDITION"],
    }
    unavailable = browser.post(route, payload)
    assert unavailable.status_code == 201
    assert unavailable.data["result"] == {"status": "insufficient", "source": None, "findings": []}
    with (
        patch("identity.medication_safety.configured_provider", return_value=SyntheticProvider()),
    ):
        assert outside.post(route, payload).status_code == 404
        assert (
            browser.post(route, {**payload, "context_confirmed": False}).data["result"]["status"]
            == "insufficient"
        )
        assert (
            browser.post(route, {**payload, "medications": payload["medications"] * 11}).status_code
            == 400
        )
        evaluated = browser.post(route, payload)
        assert evaluated.status_code == 201, evaluated.content
        unknown = browser.post(
            route,
            {
                **payload,
                "medications": [{**payload["medications"][0], "unit": "mmol"}],
            },
        )
        assert unknown.data["result"]["status"] == "insufficient"
        no_findings = browser.post(
            route,
            {
                **payload,
                "medications": [payload["medications"][1]],
                "conditions": [],
            },
        )
        assert no_findings.data["result"]["status"] == "no_findings"
    assert evaluated.data["result"]["status"] == "findings"
    assert evaluated.data["result"]["source"]["version"] == "1"
    assert {row["kind"] for row in evaluated.data["result"]["findings"]} == {
        "allergy",
        "contraindication",
        "duplication",
        "interaction",
        "maximum_dose",
    }
    assert all(row["evidence_level"] == "synthetic" for row in evaluated.data["result"]["findings"])
    override = f"clinical/medication-checks/{evaluated.data['id']}/override/"
    reason = {"patient": str(record.pk), "reason": "Synthetic exercise"}
    assert outside.post(override, reason).status_code == 404
    assert browser.post(override, {**reason, "patient": str(org.pk)}).status_code == 400
    assert (
        browser.post(
            f"clinical/medication-checks/{unavailable.data['id']}/override/", reason
        ).status_code
        == 400
    )
    assert browser.post(override, reason).status_code == 200
    assert browser.post(override, reason).status_code == 200
    assert AuditEvent.objects.filter(action="clinical.medication_override_recorded").count() == 1
    with pytest.raises(DatabaseError), transaction.atomic():
        MedicationSafetyOverride.objects.all().update(reason="changed")
    with patch("identity.medication_safety.configured_provider") as adapter:
        adapter.return_value.snapshot.side_effect = MedicationSourceUnavailable
        assert browser.post(route, payload).data["result"]["status"] == "insufficient"
