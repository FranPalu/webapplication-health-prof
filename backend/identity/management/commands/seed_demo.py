from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from identity.models import Organization, Patient


class Command(BaseCommand):
    help = "Create idempotent synthetic fixtures; no login credentials or verified professionals."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Synthetic seed is development-only")
        org, _ = Organization.objects.get_or_create(
            id="00000000-0000-4000-8000-000000000001",
            defaults={"name": "Clinica DIMOSTRATIVA — dati fittizi", "kind": "clinic"},
        )
        for index in range(1, 4):
            Patient.objects.get_or_create(
                legacy_source="synthetic-seed",
                legacy_owner="demo",
                legacy_id=str(index),
                defaults={
                    "organization": org,
                    "first_name": f"Paziente Fittizio {index}",
                    "last_name": "DIMOSTRATIVO",
                    "birth_date": date(1990, 1, index),
                    "email": f"patient{index}@patients.example",
                },
            )
        self.stdout.write(
            "Synthetic organization and 3 patients ready; no account credentials created."
        )
