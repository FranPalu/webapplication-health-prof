from datetime import timedelta

import pytest
from django.utils import timezone
from test_identity import approve, org_for, patient, signed, user

from identity.models import Membership, PaymentOrder

pytestmark = pytest.mark.django_db


@pytest.mark.django_db(transaction=True)
def test_booking_excludes_overlaps_and_refunds_on_cancellation():
    administrator = user("agenda-admin@patients.example", "organization_admin")
    org = org_for(administrator)
    admin = signed(administrator)
    clinician = user("agenda-clinician@patients.example", "professional")
    approve(clinician)
    Membership.objects.create(organization=org, user=clinician, role="professional")
    customers = [user(f"agenda-{i}@patients.example") for i in range(2)]
    for account in customers:
        record = patient(org)
        record.account = account
        record.save(update_fields=["account"])
    first, second = (signed(account) for account in customers)

    price = admin.post(
        f"organizations/{org.pk}/payment-prices/",
        {
            "title": "Test",
            "amount": 5000,
        },
    ).data["id"]
    import uuid

    order = first.post(
        "payments/checkout/",
        {
            "price": price,
            "request_id": str(uuid.uuid4()),
            "outcome": "paid",
        },
    ).data["id"]
    start = timezone.now() + timedelta(days=1)
    payload = {
        "title": "Synthetic appointment",
        "professional": str(clinician.pk),
        "price": price,
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(minutes=30)).isoformat(),
    }
    route = f"organizations/{org.pk}/appointment-slots/"
    slot = admin.post(route, payload)
    assert slot.status_code == 201, slot.content
    assert admin.post(route, payload).status_code == 409
    assert first.get(route).data["count"] == 1
    booking_route = f"appointments/slots/{slot.data['id']}/book/"
    booking = first.post(booking_route, {"payment": order})
    assert booking.status_code == 201, booking.content
    assert first.post(booking_route, {"payment": order}).status_code == 200
    assert second.post(booking_route, {}).status_code == 409
    assert admin.post(f"payments/orders/{order}/refund/", {}).status_code == 409
    cancel = f"appointments/bookings/{booking.data['id']}/cancel/"
    assert second.post(cancel, {}).status_code == 404
    assert first.post(cancel, {}).status_code == 200
    assert PaymentOrder.objects.get(pk=order).simulation_status == "refunded"
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections

    gate = Barrier(2)

    def compete(browser):
        close_old_connections()
        try:
            gate.wait(timeout=5)
            return browser.post(booking_route, {}).status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(compete, [first, second])) == [201, 409]
