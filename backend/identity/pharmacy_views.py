import base64
from types import SimpleNamespace

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from identity import prescriptions
from identity.analysis import decode, encode
from identity.clinical_storage import read_content
from identity.models import (
    ClinicalDocument,
    ClinicalDocumentVersion,
    InAppNotification,
    Membership,
    PharmacyItem,
    PharmacyReservation,
    User,
)
from identity.security import audit, rate_limit
from identity.views import InputView


class ItemInput(serializers.Serializer):
    sku = serializers.CharField(max_length=64)
    title = serializers.CharField(max_length=120)
    stock = serializers.IntegerField(min_value=0, max_value=100000)
    prescription_required = serializers.BooleanField(default=True)


class ItemOutput(serializers.ModelSerializer):
    available = serializers.SerializerMethodField()

    def get_available(self, item) -> bool:
        return item.stock > 0

    class Meta:
        model = PharmacyItem
        fields = ("id", "sku", "title", "available", "prescription_required")


class ReserveInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=10)
    prescription_version = serializers.UUIDField(required=False)
    nre = serializers.RegexField(r"^[0-9A-Z]{15}$", required=False)


class PharmacyDecisionInput(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["confirmed", "rejected"])


class ReservationOutput(serializers.ModelSerializer):
    class Meta:
        model = PharmacyReservation
        fields = ("id", "item", "quantity", "state", "created_at")


def pharmacies(request):
    if request.session.get("mfa_version") != request.user.auth_version:
        raise PermissionDenied()
    return Membership.objects.filter(
        user=request.user, active=True, role="admin", organization__kind="pharmacy"
    ).values("organization_id")


class CatalogView(InputView):
    serializer_class = ItemInput

    @extend_schema(responses=ItemOutput(many=True))
    def get(self, request, org_id):
        items = PharmacyItem.objects.filter(pharmacy_id=org_id).order_by("sku", "pk")
        return self.get_paginated_response(
            ItemOutput(self.paginate_queryset(items), many=True).data
        )

    @extend_schema(responses=ItemOutput)
    @transaction.atomic
    def post(self, request, org_id):
        from identity.models import Organization

        org = get_object_or_404(Organization.objects.filter(pk__in=pharmacies(request)), pk=org_id)
        data = self.data(request)
        item, _ = PharmacyItem.objects.update_or_create(
            pharmacy=org, sku=data.pop("sku"), defaults=data
        )
        audit(request.user, "pharmacy.catalog_updated", item.pk, org)
        return Response(ItemOutput(item).data)


class ReserveView(InputView):
    serializer_class = ReserveInput

    @extend_schema(responses={201: ReservationOutput, 200: ReservationOutput})
    @transaction.atomic
    def post(self, request, item_id):
        if request.user.role != "patient":
            raise PermissionDenied()
        rate_limit(request, "pharmacy-reserve", limit=12)
        data = self.data(request)
        # Serialize a patient's idempotency keys even when they refer to different items.
        User.objects.select_for_update().get(pk=request.user.pk)
        existing = PharmacyReservation.objects.filter(
            requester=request.user, request_id=data["request_id"]
        ).first()
        if existing:
            if existing.item_id != item_id or existing.quantity != data["quantity"]:
                return Response({"code": "reservation_conflict"}, status=409)
            return Response(ReservationOutput(existing).data)
        item = get_object_or_404(PharmacyItem.objects.select_for_update(), pk=item_id)
        nre = data.pop("nre", None)
        version_id = data.pop("prescription_version", None)
        if item.prescription_required and (
            not (nre or version_id) or prescriptions.verifier is None
        ):
            return Response({"code": "prescription_verification_unavailable"}, status=409)
        if (nre or version_id) and not item.prescription_required:
            return Response({"code": "prescription_not_required"}, status=400)
        version = None
        if version_id:
            version = get_object_or_404(
                ClinicalDocumentVersion.objects.defer("ciphertext", "wrapped_key"),
                pk=version_id,
                document__patient__account=request.user,
                document__kind=ClinicalDocument.Kind.PRESCRIPTION,
                document__deleted_at__isnull=True,
                purged_at__isnull=True,
                media_type="application/pdf",
            )
        encrypted = None
        if nre:
            sealed = encode({"nre": nre}, item.pharmacy_id)
            encrypted = {
                key: base64.b64encode(value).decode() if isinstance(value, bytes) else value
                for key, value in sealed.items()
            }
        if item.stock < data["quantity"]:
            return Response({"code": "insufficient_stock"}, status=409)
        item.stock -= data["quantity"]
        item.save(update_fields=["stock"])
        reservation = PharmacyReservation.objects.create(
            item=item,
            requester=request.user,
            prescription=encrypted,
            prescription_version=version,
            **data,
        )
        audit(request.user, "pharmacy.reserved", reservation.pk, item.pharmacy)
        return Response(ReservationOutput(reservation).data, status=201)


class ReservationListView(InputView):
    serializer_class = ReservationOutput

    @extend_schema(responses=ReservationOutput(many=True))
    def get(self, request):
        rows = PharmacyReservation.objects.filter(requester=request.user).order_by(
            "-created_at", "-pk"
        )
        return self.get_paginated_response(
            ReservationOutput(self.paginate_queryset(rows), many=True).data
        )


class PharmacyQueueView(InputView):
    serializer_class = ReservationOutput

    @extend_schema(responses=ReservationOutput(many=True))
    def get(self, request, org_id):
        rows = PharmacyReservation.objects.filter(
            item__pharmacy_id=org_id, item__pharmacy_id__in=pharmacies(request), state="pending"
        ).order_by("created_at", "pk")
        return self.get_paginated_response(
            ReservationOutput(self.paginate_queryset(rows), many=True).data
        )


class PharmacyDecisionView(InputView):
    serializer_class = PharmacyDecisionInput

    @extend_schema(responses=ReservationOutput)
    @transaction.atomic
    def post(self, request, reservation_id):
        reservation = get_object_or_404(
            PharmacyReservation.objects.select_for_update(of=("self",)).filter(
                item__pharmacy_id__in=pharmacies(request)
            ),
            pk=reservation_id,
        )
        decision = self.data(request)["decision"]
        if reservation.state == decision:
            return Response(ReservationOutput(reservation).data)
        if reservation.state != "pending":
            return Response({"code": "reservation_already_decided"}, status=409)
        item = PharmacyItem.objects.select_for_update().get(pk=reservation.item_id)
        if decision == "confirmed" and (
            item.prescription_required
            or reservation.prescription
            or reservation.prescription_version_id
        ):
            verifier = prescriptions.verifier
            if verifier is None:
                return Response({"code": "prescription_verification_unavailable"}, status=409)
            nre = None
            if reservation.prescription:
                payload = dict(reservation.prescription)
                for key in ("ciphertext", "wrapped_key"):
                    payload[key] = base64.b64decode(payload[key])
                context = SimpleNamespace(patient=SimpleNamespace(organization_id=item.pharmacy_id))
                nre = decode(SimpleNamespace(**payload), context)["nre"]
            attachment = None
            if reservation.prescription_version_id:
                version = (
                    ClinicalDocumentVersion.objects.select_for_update(
                        of=("self", "document", "document__patient")
                    )
                    .select_related("document__patient")
                    .filter(
                        pk=reservation.prescription_version_id,
                        document__patient__account_id=reservation.requester_id,
                        document__kind=ClinicalDocument.Kind.PRESCRIPTION,
                        document__deleted_at__isnull=True,
                        purged_at__isnull=True,
                    )
                    .first()
                )
                if version is None:
                    return Response({"code": "prescription_unavailable"}, status=409)
                attachment = read_content(version)
            if not (nre or attachment) or not verifier.verified(
                reference=nre,
                attachment=attachment,
                requester_id=str(reservation.requester_id),
                pharmacy_id=str(item.pharmacy_id),
                sku=item.sku,
            ):
                return Response({"code": "prescription_not_verified"}, status=409)
        reservation.prescription = None
        reservation.prescription_version = None
        if decision == "rejected":
            item.stock += reservation.quantity
            item.save(update_fields=["stock"])
        reservation.state = decision
        reservation.save(update_fields=["state", "prescription", "prescription_version"])
        InAppNotification.objects.create(
            user=reservation.requester,
            category="pharmacy." + decision,
            resource_id=reservation.pk,
        )
        audit(request.user, "pharmacy." + decision, reservation.pk, item.pharmacy)
        return Response(ReservationOutput(reservation).data)
