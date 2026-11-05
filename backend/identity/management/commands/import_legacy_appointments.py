import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from identity.appointment_views import SlotInput
from identity.models import AppointmentBooking, AppointmentSlot, Membership, Patient, User
from identity.security import audit
from identity.services import verified_professional


class Command(BaseCommand):
    help = "Import reviewed legacy agenda JSON with explicit owner and account mappings."

    def add_arguments(self, parser):
        parser.add_argument("manifest", type=Path)
        parser.add_argument("--apply", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            rows = json.loads(options["manifest"].read_text())
            if not isinstance(rows, list) or len(rows) > 10000:
                raise ValueError
        except (ValueError, OSError) as exc:
            raise CommandError("Invalid manifest.") from exc

        created = 0
        for index, row in enumerate(rows, 1):
            try:
                created += self.import_row(row)
            except (
                KeyError,
                TypeError,
                ValueError,
                User.DoesNotExist,
                Patient.DoesNotExist,
            ) as exc:
                raise CommandError(f"Invalid mapping or conflict on row {index}.") from exc
        if not options["apply"]:
            transaction.set_rollback(True)
        self.stdout.write(f"{'Imported' if options['apply'] else 'Validated'} {created} new rows.")

    def import_row(self, row):
        if row["state"] != "booked":
            raise ValueError
        patient = Patient.objects.get(
            legacy_source=row["source"],
            legacy_owner=row["owner"],
            legacy_id=row["patient_legacy_id"],
            organization_id=row["organization"],
            account__isnull=False,
        )
        if patient.account_id is None:
            raise ValueError
        fields = SlotInput(data=row)
        if not fields.is_valid():
            raise ValueError
        data = fields.validated_data
        if data.get("price") or data["ends_at"] <= data["starts_at"]:
            raise ValueError
        professional = User.objects.select_for_update().get(
            pk=data.pop("professional"), is_active=True
        )
        if (
            not verified_professional(professional)
            or not Membership.objects.filter(
                user=professional,
                organization=patient.organization,
                role="professional",
                active=True,
            ).exists()
        ):
            raise ValueError
        identifier = uuid5(
            NAMESPACE_URL,
            "claria-agenda:"
            + json.dumps([row["source"], row["owner"], row["legacy_id"]], separators=(",", ":")),
        )
        existing = AppointmentSlot.objects.filter(pk=identifier).first()
        if existing:
            if (
                existing.organization_id != patient.organization_id
                or existing.professional_id != professional.pk
                or existing.starts_at != data["starts_at"]
                or existing.ends_at != data["ends_at"]
                or not existing.bookings.filter(payer_id=patient.account_id).exists()
            ):
                raise ValueError
            return 0
        if AppointmentSlot.objects.filter(
            professional=professional,
            starts_at__lt=data["ends_at"],
            ends_at__gt=data["starts_at"],
        ).exists():
            raise ValueError
        slot = AppointmentSlot.objects.create(
            id=identifier,
            organization=patient.organization,
            professional=professional,
            **data,
        )
        booking = AppointmentBooking.objects.create(slot=slot, payer_id=patient.account_id)
        audit(None, "appointment.imported", booking.pk, patient.organization)
        return 1
