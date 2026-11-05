from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from identity.models import AppointmentBooking, Membership, Patient, PaymentOrder, PaymentPrice
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
    outcome = serializers.ChoiceField(choices=["paid", "declined", "cancelled"])


class OrderOutput(serializers.ModelSerializer):
    class Meta:
        model = PaymentOrder
        fields = ("id", "amount", "simulation_status", "paid_at", "created_at")


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

    @extend_schema(responses={201: OrderOutput, 200: OrderOutput})
    @transaction.atomic
    def post(self, request):
        rate_limit(request, "payment-checkout", limit=12)
        data = self.data(request)
        orgs = Patient.objects.filter(account=request.user).values("organization_id")
        price = get_object_or_404(
            PaymentPrice.objects.filter(organization_id__in=orgs, active=True), pk=data["price"]
        )
        outcome = data["outcome"]
        order, created = PaymentOrder.objects.get_or_create(
            payer=request.user,
            request_id=data["request_id"],
            defaults={
                "price": price,
                "amount": price.amount,
                "fee": price.fee,
                "simulation_status": outcome,
                "paid_at": timezone.now() if outcome == "paid" else None,
            },
        )
        current = order.simulation_status
        if current == "refunded":
            current = "paid"
        if order.price_id != price.pk or current != outcome:
            return Response({"code": "checkout_conflict"}, status=409)
        if created:
            audit(request.user, "payment.simulated_" + outcome, order.pk, price.organization)
        return Response(OrderOutput(order).data, status=201 if created else 200)


class RefundView(InputView):
    serializer_class = OrderOutput

    @extend_schema(request=None, responses=OrderOutput)
    @transaction.atomic
    def post(self, request, order_id):
        if request.session.get("mfa_version") != request.user.auth_version:
            raise PermissionDenied()
        orgs = Membership.objects.filter(user=request.user, active=True, role="admin").values(
            "organization_id"
        )
        order = get_object_or_404(
            PaymentOrder.objects.select_for_update(of=("self",)).filter(
                price__organization_id__in=orgs,
                simulation_status__in=["paid", "refunded"],
            ),
            pk=order_id,
        )
        if AppointmentBooking.objects.filter(payment=order, cancelled_at__isnull=True).exists():
            return Response({"code": "cancel_booking_first"}, status=409)
        if order.simulation_status == "paid":
            order.simulation_status = "refunded"
            order.save(update_fields=["simulation_status"])
            audit(request.user, "payment.simulated_refund", order.pk, order.price.organization)
        return Response(OrderOutput(order).data)


class OrdersView(InputView):
    serializer_class = OrderOutput

    @extend_schema(responses=OrderOutput(many=True))
    def get(self, request):
        orders = PaymentOrder.objects.filter(payer=request.user).order_by("-created_at", "-pk")
        return self.get_paginated_response(
            OrderOutput(self.paginate_queryset(orders), many=True).data
        )
