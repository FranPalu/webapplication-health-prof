"""Sandbox Stripe Connect adapter and signed event reconciliation."""

import hashlib
import hmac
import json
import re
import time
from typing import Protocol
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from identity.models import PaymentEvent, PaymentOrder
from identity.security import audit


class PaymentUnavailable(APIException):
    status_code = 503
    default_detail = "Payment sandbox unavailable."


def require_sandbox():
    if not (
        settings.DEBUG
        and settings.STRIPE_TEST_KEY.startswith("sk_test_")
        and settings.STRIPE_WEBHOOK_SECRET.startswith("whsec_")
    ):
        raise PaymentUnavailable()


class PaymentProvider(Protocol):
    def checkout(self, order: PaymentOrder) -> tuple[str, str]: ...


class StripeSandbox:
    def checkout(self, order):
        require_sandbox()
        request = Request(
            "https://api.stripe.com/v1/checkout/sessions",
            data=urlencode(
                {
                    "mode": "payment",
                    "payment_method_types[0]": "card",
                    "success_url": settings.PUBLIC_ORIGIN + "/",
                    "cancel_url": settings.PUBLIC_ORIGIN + "/",
                    "client_reference_id": str(order.pk),
                    "line_items[0][quantity]": 1,
                    "line_items[0][price_data][currency]": "eur",
                    "line_items[0][price_data][unit_amount]": order.amount,
                    "line_items[0][price_data][product_data][name]": "Clarìa",
                    "payment_intent_data[transfer_data][destination]": order.destination,
                    "payment_intent_data[application_fee_amount]": order.fee,
                }
            ).encode(),
            headers={
                "Authorization": "Bearer " + settings.STRIPE_TEST_KEY,
                "Stripe-Version": "2025-02-24.acacia",
                "Idempotency-Key": "claria-checkout-" + str(order.pk),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                data = json.loads(response.read(65536))
            parsed = urlsplit(data["url"])
            if parsed.scheme != "https" or parsed.netloc != "checkout.stripe.com":
                raise ValueError
            if data["livemode"] is not False or not data["id"].startswith("cs_test_"):
                raise ValueError
            return data["id"], data["url"]
        except (URLError, TimeoutError, ValueError, KeyError, TypeError) as exc:
            raise PaymentUnavailable() from exc


provider: PaymentProvider = StripeSandbox()


def verified_event(body, signature, secret, now=None):
    header: dict[str, list[str]] = {}
    for item in signature.split(","):
        key, separator, value = item.partition("=")
        if separator:
            header.setdefault(key, []).append(value)
    (timestamp,) = header["t"]
    if abs((time.time() if now is None else now) - int(timestamp)) > 300:
        raise ValueError("Stale signature")
    signed = timestamp.encode() + b"." + body
    expected = hmac.digest(secret.encode(), signed, hashlib.sha256).hex()
    if not any(
        hmac.compare_digest(expected, candidate)
        for candidate in header.get("v1", [])
        if re.fullmatch("[0-9a-f]{64}", candidate)
    ):
        raise ValueError("Invalid signature")
    return json.loads(body)


@transaction.atomic
def reconcile_checkout(event):
    if event.get("livemode") is not False or event.get("type") not in (
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    ):
        return
    session = event["data"]["object"]
    if session.get("payment_status") != "paid":
        return
    order = (
        PaymentOrder.objects.select_for_update(of=("self",))
        .select_related("price__organization")
        .filter(pk=session["client_reference_id"])
        .first()
    )
    if order is None:
        return
    if (
        not order.checkout_session
        or order.checkout_session != session["id"]
        or session["amount_total"] != order.amount
        or session["currency"] != "eur"
        or session["mode"] != "payment"
    ):
        raise ValueError("Checkout mismatch")
    _, created = PaymentEvent.objects.get_or_create(
        provider_id=event["id"], defaults={"order": order}
    )
    if created and order.paid_at is None:
        order.paid_at = timezone.now()
        order.save(update_fields=["paid_at"])
        audit(None, "payment.sandbox_paid", order.pk, order.price.organization)
