import uuid

import pytest
from test_identity import org_for, signed, user

from identity.models import InAppNotification

pytestmark = pytest.mark.django_db


def test_pharmacy_stock_rejection_and_prescription_gate():
    owner = user("pharmacy-owner@patients.example", "organization_admin")
    org = org_for(owner)
    org.kind = "pharmacy"
    org.save(update_fields=["kind"])
    pharmacy = signed(owner)
    first = signed(user("pharmacy-first@patients.example"))
    second = signed(user("pharmacy-second@patients.example"))
    catalog = f"organizations/{org.pk}/pharmacy/catalog/"
    otc = pharmacy.post(
        catalog,
        {
            "sku": "TEST",
            "title": "Synthetic product",
            "stock": 1,
            "prescription_required": False,
        },
    ).data["id"]
    rx = pharmacy.post(
        catalog,
        {
            "sku": "RX",
            "title": "Synthetic prescription product",
            "stock": 1,
        },
    ).data["id"]
    body = {"request_id": str(uuid.uuid4()), "quantity": 1}
    assert first.post(f"pharmacy/items/{rx}/reserve/", body).status_code == 409
    path = f"pharmacy/items/{otc}/reserve/"
    reservation = first.post(path, body)
    assert reservation.status_code == 201, reservation.content
    assert first.post(path, body).status_code == 200
    assert second.post(path, body).status_code == 409
    decision = f"pharmacy/reservations/{reservation.data['id']}/decision/"
    assert first.post(decision, {"decision": "rejected"}).status_code == 403
    assert pharmacy.post(decision, {"decision": "rejected"}).status_code == 200
    assert pharmacy.post(decision, {"decision": "rejected"}).status_code == 200
    assert InAppNotification.objects.filter(category="pharmacy.rejected").count() == 1
    next_reservation = second.post(path, body)
    assert next_reservation.status_code == 201
    assert (
        pharmacy.post(
            f"pharmacy/reservations/{next_reservation.data['id']}/decision/",
            {"decision": "confirmed"},
        ).status_code
        == 200
    )


def test_prescription_attachment_only_reaches_verifier_for_its_owner(settings):
    from unittest.mock import Mock, patch

    from cryptography.fernet import Fernet
    from test_clinical import PDF
    from test_identity import patient

    from identity.clinical import seal
    from identity.models import ClinicalDocument, ClinicalDocumentVersion, PharmacyReservation

    settings.CLINICAL_MASTER_KEY = Fernet.generate_key().decode()
    owner = user("rx-admin@patients.example", "organization_admin")
    org = org_for(owner)
    org.kind = "pharmacy"
    org.save(update_fields=["kind"])
    pharmacy = signed(owner)
    account = user("rx-owner@patients.example")
    buyer = signed(account)
    outsider = signed(user("rx-outsider@patients.example"))
    record = patient(org)
    record.account = account
    record.save(update_fields=["account"])
    document = ClinicalDocument.objects.create(patient=record, author=owner, kind="prescription")
    version = ClinicalDocumentVersion.objects.create(
        document=document,
        number=1,
        title="Synthetic",
        media_type="application/pdf",
        size=len(PDF),
        **seal(PDF, org.pk),
    )
    item = pharmacy.post(
        f"organizations/{org.pk}/pharmacy/catalog/",
        {
            "sku": "RX",
            "title": "Synthetic",
            "stock": 1,
        },
    ).data["id"]
    path = f"pharmacy/items/{item}/reserve/"
    payload = {
        "quantity": 1,
        "request_id": str(uuid.uuid4()),
        "prescription_version": str(version.pk),
    }
    assert buyer.post(path, payload).status_code == 409
    verifier = Mock()
    verifier.verified.return_value = False
    with patch("identity.prescriptions.verifier", verifier):
        assert outsider.post(path, payload).status_code == 404
        result = buyer.post(path, payload)
        assert result.status_code == 201, result.content
        assert "prescription_version" not in result.data
        assert pharmacy.get(f"clinical/versions/{version.pk}/download/").status_code == 404
        route = f"pharmacy/reservations/{result.data['id']}/decision/"
        assert pharmacy.post(route, {"decision": "confirmed"}).status_code == 409
        verifier.verified.assert_called_once_with(
            reference=None,
            attachment=PDF,
            requester_id=str(account.pk),
            pharmacy_id=str(org.pk),
            sku="RX",
        )
        verifier.verified.return_value = True
        assert pharmacy.post(route, {"decision": "confirmed"}).status_code == 200
        assert PharmacyReservation.objects.get().prescription_version_id is None
