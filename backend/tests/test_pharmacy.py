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
