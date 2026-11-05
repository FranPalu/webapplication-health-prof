import uuid

import pytest
from test_identity import org_for, patient, signed, user

from identity.models import PaymentOrder

pytestmark = pytest.mark.django_db


def test_internal_payment_and_refund_are_scoped_and_idempotent():
    admin = user("sandbox-admin@patients.example", "organization_admin")
    org = org_for(admin)
    owner = signed(admin)
    payer = user("sandbox-payer@patients.example")
    record = patient(org)
    record.account = payer
    record.save(update_fields=["account"])
    buyer = signed(payer)
    outsider = signed(user("outside-payer@patients.example"))
    prices = f"organizations/{org.pk}/payment-prices/"
    created = owner.post(prices, {"title": "Synthetic service", "amount": 7000, "fee": 100})
    assert created.status_code == 201
    assert buyer.get(prices).data["count"] == 1
    assert outsider.get(prices).status_code == 403
    request = {"price": created.data["id"], "request_id": str(uuid.uuid4()), "outcome": "paid"}
    assert outsider.post("payments/checkout/", request).status_code == 404
    first = buyer.post("payments/checkout/", request)
    assert first.status_code == 201
    assert first.data["simulation_status"] == "paid"
    assert "url" not in first.data
    assert buyer.post("payments/checkout/", request).status_code == 200
    assert buyer.post("payments/checkout/", {**request, "outcome": "cancelled"}).status_code == 409
    assert PaymentOrder.objects.count() == 1
    assert PaymentOrder.objects.get().checkout_session == ""
    for outcome in ("declined", "cancelled"):
        result = buyer.post(
            "payments/checkout/",
            {
                **request,
                "request_id": str(uuid.uuid4()),
                "outcome": outcome,
            },
        )
        assert result.status_code == 201
        assert result.data["simulation_status"] == outcome and result.data["paid_at"] is None
    path = f"payments/orders/{first.data['id']}/refund/"
    assert buyer.post(path, {}).status_code == 403
    assert owner.post(path, {}).data["simulation_status"] == "refunded"
    assert owner.post(path, {}).data["simulation_status"] == "refunded"
    assert buyer.post("payments/checkout/", request).data["simulation_status"] == "refunded"
    assert outsider.get("payments/orders/").data["count"] == 0
    assert buyer.post("payments/stripe/webhook/", {}).status_code == 404
