import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.core.validators import URLValidator
from django.db import transaction

from identity.models import ResearchTerminology
from identity.security import audit

LOINC = re.compile(r"[0-9]{1,12}-[0-9]")
SYSTEMS = {"loinc", "snomed-ct", "icd-10"}


class Command(BaseCommand):
    help = "Validate and import reviewed terminology metadata and optional LOINC mappings."

    def add_arguments(self, parser):
        parser.add_argument("manifest", type=Path)
        parser.add_argument("--apply", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            rows = json.loads(options["manifest"].read_text())
            if not isinstance(rows, list) or len(rows) > 10000:
                raise ValueError
        except (ValueError, OSError):
            raise CommandError("Invalid terminology manifest.") from None
        validated = {}
        for index, row in enumerate(rows, 1):
            try:
                system, code = row["system"], row["code"]
                version, source, license_url = row["version"], row["source"], row["license"]
                target = row.get("loinc_target", "")
                active = row.get("active", True)
                if (
                    system not in SYSTEMS
                    or not 0 < len(code) <= 32
                    or not 0 < len(version) <= 40
                    or not isinstance(active, bool)
                    or (system == "loinc" and not LOINC.fullmatch(code))
                    or (target and not LOINC.fullmatch(target))
                    or (system, code) in validated
                ):
                    raise ValueError
                validator = URLValidator(schemes=["https"])
                for url in (source, license_url):
                    if len(url) > 200:
                        raise ValueError
                    validator(url)
                validated[(system, code)] = {
                    "version": version,
                    "source": source,
                    "license": license_url,
                    "loinc_target": target,
                    "active": active,
                }
            except Exception:
                raise CommandError(f"Invalid terminology metadata on row {index}.") from None
        for row in validated.values():
            target = row["loinc_target"]
            if (
                target
                and ("loinc", target) not in validated
                and not ResearchTerminology.objects.filter(
                    system="loinc", code=target, active=True
                ).exists()
            ):
                raise CommandError("A mapping target is absent from the LOINC catalog.")
        if options["apply"]:
            for (system, code), row in validated.items():
                ResearchTerminology.objects.update_or_create(system=system, code=code, defaults=row)
            audit(None, "research.terminology_imported")
        self.stdout.write(
            f"{'Imported' if options['apply'] else 'Validated'} {len(validated)} terms."
        )
