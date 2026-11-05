import json
import re
from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from identity import payments
from identity.models import Membership, Patient, PaymentOrder, PaymentPrice
from identity.security import audit, rate_limit
from identity.views import InputView


class PriceOutput(serializers.ModelSerializer):
    class Meta:
        model = PaymentPrice
        fields = ("id", "title", "amount", "fee", "active")
        extra_kwargs = {
            "amount": {"min_value": 50, "max_value": 99999999},
            "fee": {"min_value": 0, "max_value": 99999999},
        }

    def validate(self, attrs):
        if attrs.get("fee", 0) >= attrs["amount"]:
            raise ValidationError("Fee must be lower than total.")
        return attrs


class CheckoutInput(serializers.Serializer):
    price = serializers.UUIDField()
    request_id = serializers.UUIDField()


class CheckoutOutput(serializers.Serializer):
    id = serializers.UUIDField()
    url = serializers.URLField()


class OrderOutput(serializers.ModelSerializer):
    class Meta:
        model = PaymentOrder
        fields = ("id", "amount", "paid_at", "created_at")


class PriceView(InputView):
    serializer_class = PriceOutput

    @extend_schema(responses=PriceOutput(many=True))
    def get(self, request, org_id):
        if not Patient.objects.filter(account=request.user, organization_id=org_id).exists():
            raise PermissionDenied()
        prices = PaymentPrice.objects.filter(organization_id=org_id, active=True).order_by("pk")
        return self.get_paginated_response(
            PriceOutput(self.paginate_queryset(prices), many=True).data
        )

    @transaction.atomic
    @extend_schema(responses={201: PriceOutput})
    def post(self, request, org_id):
        if request.session.get("mfa_version") != request.user.auth_version:
            raise PermissionDenied()
        membership = get_object_or_404(
            Membership, user=request.user, organization_id=org_id, role="admin", active=True
        )
        price = PaymentPrice.objects.create(
            organization=membership.organization, **self.data(request)
        )
        audit(request.user, "payment.price_created", price.pk, membership.organization)
        return Response(PriceOutput(price).data, status=201)


class CheckoutView(InputView):
    serializer_class = CheckoutInput

    @extend_schema(responses={201: CheckoutOutput})
    def post(self, request):
        payments.require_sandbox()
        rate_limit(request, "payment-checkout", limit=12)
        data = self.data(request)
        orgs = Patient.objects.filter(account=request.user).values("organization_id")
        price = get_object_or_404(
            PaymentPrice.objects.filter(organization_id__in=orgs, active=True), pk=data["price"]
        )
        from django.conf import settings

        try:
            destination = json.loads(settings.STRIPE_TEST_DESTINATIONS).get(
                str(price.organization_id)
            )
        except (ValueError, AttributeError) as exc:
            raise payments.PaymentUnavailable() from exc
        if not isinstance(destination, str) or not re.fullmatch(
            r"acct_[A-Za-z0-9]{1,70}", destination
        ):
            raise payments.PaymentUnavailable()
        order, _ = PaymentOrder.objects.get_or_create(
            payer=request.user,
            request_id=data["request_id"],
            defaults={
                "price": price,
                "amount": price.amount,
                "fee": price.fee,
                "destination": destination,
            },
        )
        if (
            order.price_id != price.pk
            or order.paid_at
            or order.created_at < timezone.now() - timedelta(hours=23)
        ):
            return Response({"code": "checkout_conflict"}, status=409)
        session, url = payments.provider.checkout(order)
        if order.checkout_session and order.checkout_session != session:
            raise payments.PaymentUnavailable()
        PaymentOrder.objects.filter(pk=order.pk, checkout_session="").update(
            checkout_session=session
        )
        return Response({"id": str(order.pk), "url": url}, status=201)


class OrdersView(InputView):
    serializer_class = OrderOutput

    @extend_schema(responses=OrderOutput(many=True))
    def get(self, request):
        orders = PaymentOrder.objects.filter(payer=request.user).order_by("-created_at", "-pk")
        return self.get_paginated_response(
            OrderOutput(self.paginate_queryset(orders), many=True).data
        )


@csrf_exempt
@require_POST
def stripe_webhook(request):
    from django.conf import settings

    try:
        payments.require_sandbox()
        event = payments.verified_event(
            request.body,
            request.headers.get("Stripe-Signature", ""),
            settings.STRIPE_WEBHOOK_SECRET,
        )
        payments.reconcile_checkout(event)
    except payments.PaymentUnavailable:
        return JsonResponse({"code": "sandbox_unavailable"}, status=503)
    except (ValueError, KeyError, TypeError, AttributeError, DjangoValidationError):
        return JsonResponse({"code": "invalid_event"}, status=400)
    return JsonResponse({"received": True})
