import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from identity.models import Organization, PharmacyItem
from identity.pharmacy_views import ItemInput
from identity.security import audit


class Command(BaseCommand):
    help = "Validate or import a pharmacy catalog CSV. Dry run by default."

    def add_arguments(self, parser):
        parser.add_argument("pharmacy")
        parser.add_argument("file", type=Path)
        parser.add_argument("--apply", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        org = Organization.objects.filter(pk=options["pharmacy"], kind="pharmacy").first()
        if org is None:
            raise CommandError("Unknown pharmacy.")
        rows, errors, seen = [], [], set()
        with options["file"].open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not {"sku", "title", "stock", "prescription_required"} <= set(
                reader.fieldnames or []
            ):
                raise CommandError("Missing CSV columns.")
            for index, row in enumerate(reader, 2):
                if index > 10001:
                    raise CommandError("CSV exceeds 10000 rows.")
                data = ItemInput(data=row)
                if not data.is_valid():
                    errors.append(f"Line {index}: invalid fields: {', '.join(data.errors)}")
                elif data.validated_data["sku"] in seen:
                    errors.append(f"Line {index}: duplicate SKU")
                else:
                    seen.add(data.validated_data["sku"])
                    rows.append(dict(data.validated_data))
        if errors:
            raise CommandError("\n".join(errors[:100]) + f"\nInvalid rows: {len(errors)}")
        if options["apply"]:
            for row in rows:
                PharmacyItem.objects.update_or_create(
                    pharmacy=org, sku=row.pop("sku"), defaults=row
                )
            audit(None, "pharmacy.catalog_imported", org.pk, org)
        self.stdout.write(f"{'Imported' if options['apply'] else 'Validated'} {len(rows)} rows.")
