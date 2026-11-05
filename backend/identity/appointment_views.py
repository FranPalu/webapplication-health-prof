from datetime import timedelta

from django.db import transaction
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from identity.models import (
    AppointmentBooking,
    AppointmentSlot,
    Membership,
    Patient,
    PaymentOrder,
    PaymentPrice,
    User,
)
from identity.security import audit
from identity.services import verified_professional
from identity.views import InputView


class SlotInput(serializers.Serializer):
    title = serializers.CharField(max_length=120)
    professional = serializers.UUIDField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    price = serializers.UUIDField(required=False)


class SlotOutput(serializers.ModelSerializer):
    class Meta:
        model = AppointmentSlot
        fields = ("id", "title", "professional", "starts_at", "ends_at", "price")


class BookingInput(serializers.Serializer):
    payment = serializers.UUIDField(required=False)


class BookingOutput(serializers.ModelSerializer):
    class Meta:
        model = AppointmentBooking
        fields = ("id", "slot", "payment", "cancelled_at", "created_at")


def patient_organizations(user):
    return Patient.objects.filter(account=user).values("organization_id")


class SlotsView(InputView):
    serializer_class = SlotInput

    @extend_schema(responses=SlotOutput(many=True))
    def get(self, request, org_id):
        slots = (
            AppointmentSlot.objects.filter(
                organization_id=org_id,
                organization_id__in=patient_organizations(request.user),
                starts_at__gt=timezone.now(),
            )
            .filter(
                ~Exists(
                    AppointmentBooking.objects.filter(
                        slot_id=OuterRef("pk"),
                        cancelled_at__isnull=True,
                    )
                )
            )
            .order_by("starts_at", "pk")
        )
        return self.get_paginated_response(
            SlotOutput(self.paginate_queryset(slots), many=True).data
        )

    @extend_schema(responses={201: SlotOutput})
    @transaction.atomic
    def post(self, request, org_id):
        if request.session.get("mfa_version") != request.user.auth_version:
            raise PermissionDenied()
        membership = get_object_or_404(
            Membership, user=request.user, organization_id=org_id, active=True, role="admin"
        )
        data = self.data(request)
        if data["starts_at"] <= timezone.now() or not timedelta(0) < (
            data["ends_at"] - data["starts_at"]
        ) <= timedelta(hours=12):
            raise ValidationError("Invalid appointment interval.")
        professional = get_object_or_404(
            User.objects.select_for_update(of=("self",)).filter(
                is_active=True,
                membership__organization_id=org_id,
                membership__role="professional",
                membership__active=True,
            ),
            pk=data.pop("professional"),
        )
        if not verified_professional(professional):
            raise PermissionDenied()
        if AppointmentSlot.objects.filter(
            professional=professional,
            starts_at__lt=data["ends_at"],
            ends_at__gt=data["starts_at"],
        ).exists():
            return Response({"code": "slot_overlap"}, status=409)
        price_id = data.pop("price", None)
        price = (
            get_object_or_404(PaymentPrice, pk=price_id, organization_id=org_id, active=True)
            if price_id
            else None
        )
        slot = AppointmentSlot.objects.create(
            organization=membership.organization,
            professional=professional,
            price=price,
            **data,
        )
        audit(request.user, "appointment.slot_created", slot.pk, membership.organization)
        return Response(SlotOutput(slot).data, status=201)


class BookSlotView(InputView):
    serializer_class = BookingInput

    @extend_schema(responses={201: BookingOutput, 200: BookingOutput})
    @transaction.atomic
    def post(self, request, slot_id):
        slot = get_object_or_404(
            AppointmentSlot.objects.select_for_update().filter(
                organization_id__in=patient_organizations(request.user),
                starts_at__gt=timezone.now(),
            ),
            pk=slot_id,
        )
        if (
            not verified_professional(slot.professional)
            or not Membership.objects.filter(
                user=slot.professional,
                user__is_active=True,
                organization=slot.organization,
                role="professional",
                active=True,
            ).exists()
        ):
            return Response({"code": "slot_unavailable"}, status=409)
        data = self.data(request)
        existing = slot.bookings.filter(cancelled_at__isnull=True).first()
        if existing:
            if existing.payer_id == request.user.pk and existing.payment_id == data.get("payment"):
                return Response(BookingOutput(existing).data)
            return Response({"code": "slot_unavailable"}, status=409)
        payment = None
        if data.get("payment"):
            if not slot.price_id:
                raise ValidationError("Slot does not accept advance payment.")
            payment = get_object_or_404(
                PaymentOrder.objects.select_for_update(),
                pk=data["payment"],
                payer=request.user,
                price_id=slot.price_id,
                simulation_status="paid",
            )
            if AppointmentBooking.objects.filter(payment=payment).exists():
                return Response({"code": "payment_used"}, status=409)
        booking = AppointmentBooking.objects.create(slot=slot, payer=request.user, payment=payment)
        audit(request.user, "appointment.booked", booking.pk, slot.organization)
        return Response(BookingOutput(booking).data, status=201)


class MyBookingsView(InputView):
    serializer_class = BookingOutput

    @extend_schema(responses=BookingOutput(many=True))
    def get(self, request):
        rows = AppointmentBooking.objects.filter(payer=request.user).order_by("-created_at", "-pk")
        return self.get_paginated_response(
            BookingOutput(self.paginate_queryset(rows), many=True).data
        )


class CancelBookingView(InputView):
    serializer_class = BookingOutput

    @extend_schema(request=None, responses=BookingOutput)
    @transaction.atomic
    def post(self, request, booking_id):
        booking = get_object_or_404(
            AppointmentBooking.objects.select_for_update().filter(
                payer=request.user,
            ),
            pk=booking_id,
        )
        if booking.cancelled_at:
            return Response(BookingOutput(booking).data)
        if booking.slot.starts_at <= timezone.now():
            return Response({"code": "appointment_started"}, status=409)
        booking.cancelled_at = timezone.now()
        booking.save(update_fields=["cancelled_at"])
        if booking.payment_id:
            payment = PaymentOrder.objects.select_for_update().get(pk=booking.payment_id)
            if payment.simulation_status == "paid":
                payment.simulation_status = "refunded"
                payment.save(update_fields=["simulation_status"])
                audit(
                    request.user, "payment.simulated_refund", payment.pk, booking.slot.organization
                )
        audit(request.user, "appointment.cancelled", booking.pk, booking.slot.organization)
        return Response(BookingOutput(booking).data)
