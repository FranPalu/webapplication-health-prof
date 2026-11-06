import pytest
from django.db import DatabaseError, transaction
from test_identity import approve, org_for, patient, signed, user

from identity.models import AuditEvent, CareRelationship, Membership, PatientReconciliation


@pytest.mark.django_db
def test_two_people_link_and_unlink_without_inheriting_access():
    author, reviewer, outsider = [
        user(f"reconcile-{i}@patients.example", "professional") for i in range(3)
    ]
    for clinician in (author, reviewer, outsider):
        approve(clinician)
    org = org_for(author)
    for member in (reviewer, outsider):
        Membership.objects.create(organization=org, user=member, role="professional")
    source, target = (patient(org, author) for _ in range(2))
    for record in (source, target):
        CareRelationship.objects.create(patient=record, professional=reviewer)
    CareRelationship.objects.create(patient=source, professional=outsider)
    proposing, reviewing, outside = (
        signed(clinician) for clinician in (author, reviewer, outsider)
    )

    def identity(record, value):
        fields = {
            "identifier_kind": "facility",
            "identifier_value": value,
            "source_birth_date": str(record.birth_date),
        }
        route = f"clinical/patients/{record.pk}/identifiers/"
        assert proposing.post(route, fields).status_code == 201
        return fields

    proof = {
        "source_identity": identity(source, "SYN-SOURCE"),
        "target_identity": identity(target, "SYN-TARGET"),
    }
    route = f"clinical/patients/{source.pk}/reconciliations/"
    payload = {**proof, "target": str(target.pk), "link": True, "reason": "Synthetic review"}
    proposal = proposing.post(route, payload)
    assert proposal.status_code == 201 and proposal.data["approved"] is False
    approval = f"clinical/reconciliations/{proposal.data['id']}/approve/"
    assert proposing.post(approval, proof).status_code == 403
    assert outside.post(approval, proof).status_code == 404
    assert (
        reviewing.post(approval, {**proof, "target_identity": proof["source_identity"]}).status_code
        == 400
    )
    assert reviewing.post(approval, proof).data["approved"] is True
    assert reviewing.post(approval, proof).status_code == 200
    assert outside.get(route).data["count"] == 0
    assert outside.get(f"fhir/Patient/{target.pk}").status_code == 404
    assert proposing.post(route, payload).status_code == 400
    reverse = proposing.post(route, {**payload, "link": False})
    assert reverse.status_code == 201
    assert (
        reviewing.post(f"clinical/reconciliations/{reverse.data['id']}/approve/", proof).status_code
        == 200
    )
    assert proposing.post(route, payload).status_code == 201
    assert (
        AuditEvent.objects.filter(
            action="clinical.reconciliation_approved", organization=org
        ).count()
        == 2
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        PatientReconciliation.objects.all().update(reason="altered")
