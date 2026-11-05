import hashlib
import hmac
import json
import time
import uuid
from unittest.mock import patch

import pytest
from django.test import Client
from test_identity import org_for, patient, signed, user

from identity.models import PaymentEvent, PaymentOrder

pytestmark = pytest.mark.django_db


def test_sandbox_checkout_and_verified_idempotent_payment(settings):
    settings.STRIPE_TEST_KEY = "sk_test_fixture"
    settings.STRIPE_WEBHOOK_SECRET = "whsec_fixture"
    admin = user("sandbox-admin@patients.example", "organization_admin")
    org = org_for(admin)
    owner = signed(admin)
    payer = user("sandbox-payer@patients.example")
    record = patient(org)
    record.account = payer
    record.save(update_fields=["account"])
    buyer = signed(payer)
    outsider = signed(user("outside-payer@patients.example"))
    settings.STRIPE_TEST_DESTINATIONS = json.dumps({str(org.pk): "acct_fixture"})
    prices = f"organizations/{org.pk}/payment-prices/"
    created = owner.post(prices, {"title": "Synthetic service", "amount": 7000, "fee": 100})
    assert created.status_code == 201
    assert buyer.get(prices).data["count"] == 1
    assert outsider.get(prices).status_code == 403
    request = {"price": created.data["id"], "request_id": str(uuid.uuid4())}
    with patch(
        "identity.payments.provider.checkout",
        return_value=("cs_test_fixture", "https://checkout.stripe.com/test"),
    ) as stripe:
        assert outsider.post("payments/checkout/", request).status_code == 404
        first = buyer.post("payments/checkout/", request)
        assert first.status_code == 201
        assert buyer.post("payments/checkout/", request).data["id"] == first.data["id"]
        assert stripe.call_count == 2
    assert PaymentOrder.objects.count() == 1
    order = PaymentOrder.objects.get()
    assert order.paid_at is None

    def deliver(event_id, amount=7000, kind="checkout.session.completed", valid=True):
        event = {
            "id": event_id,
            "type": kind,
            "livemode": False,
            "data": {
                "object": {
                    "id": order.checkout_session,
                    "client_reference_id": str(order.pk),
                    "amount_total": amount,
                    "payment_status": "paid",
                    "mode": "payment",
                    "currency": "eur",
                }
            },
        }
        body = json.dumps(event).encode()
        timestamp = str(int(time.time()))
        digest = hmac.digest(
            settings.STRIPE_WEBHOOK_SECRET.encode(),
            timestamp.encode() + b"." + body,
            hashlib.sha256,
        ).hex()
        return Client().post(
            "/api/v1/payments/stripe/webhook/",
            body,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=f"t={timestamp},v1={digest if valid else 'bad'}",
        )

    assert deliver("evt_bad", valid=False).status_code == 400
    assert deliver("evt_bad_amount", amount=10).status_code == 400
    assert deliver("evt_ok").status_code == 200
    order.refresh_from_db()
    paid = order.paid_at
    assert paid is not None
    assert deliver("evt_ok").status_code == 200
    assert deliver("evt_late", kind="checkout.session.expired").status_code == 200
    order.refresh_from_db()
    assert order.paid_at == paid
    assert PaymentEvent.objects.count() == 1
    assert outsider.get("payments/orders/").data["count"] == 0
