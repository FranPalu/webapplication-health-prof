"""Import an explicitly exported D1 patient manifest, never infer accounts or consent."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from identity.models import Organization, Patient
from identity.serializers import PatientSerializer


class Command(BaseCommand):
    help = "Validate/import legacy patient JSON. Dry-run by default; use --apply after review."

    def add_arguments(self, parser):
        parser.add_argument("manifest")
        parser.add_argument("owner_map")
        parser.add_argument("--source", required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        try:
            rows = json.loads(Path(options["manifest"]).read_text())
            mapping = json.loads(Path(options["owner_map"]).read_text())
            if not isinstance(rows, list) or not isinstance(mapping, dict) or not options["source"]:
                raise ValueError()
        except (OSError, ValueError) as exc:
            raise CommandError("Invalid manifest or owner map") from exc
        if len(options["source"]) > 100:
            raise CommandError("Source too long")
        created = updated = 0
        seen = set()
        with transaction.atomic():
            for index, row in enumerate(rows):
                try:
                    if row["kind"] != "patients":
                        raise ValueError()
                    owner, legacy_id = str(row["owner"]), str(row["id"])
                    if not owner or not legacy_id or len(owner) > 200 or len(legacy_id) > 200:
                        raise ValueError()
                    key = (owner, legacy_id)
                    if key in seen:
                        raise ValueError()
                    seen.add(key)
                    org = Organization.objects.get(pk=mapping[owner])
                    payload = row["payload"]
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    serializer = PatientSerializer(
                        data={
                            "first_name": payload["firstName"],
                            "last_name": payload["lastName"],
                            "birth_date": payload["birthDate"],
                            "email": payload.get("email", ""),
                        }
                    )
                    serializer.is_valid(raise_exception=True)
                    existing = Patient.objects.filter(
                        legacy_source=options["source"], legacy_owner=owner, legacy_id=legacy_id
                    ).first()
                    if existing and existing.organization_id != org.id:
                        raise ValueError()
                    demographics = {
                        k: payload[k]
                        for k in (
                            "sex",
                            "birthPlace",
                            "birthCode",
                            "cf",
                            "phone",
                            "address",
                            "city",
                            "zip",
                            "archived",
                        )
                        if k in payload
                    }
                    _, new = Patient.objects.update_or_create(
                        legacy_source=options["source"],
                        legacy_owner=owner,
                        legacy_id=legacy_id,
                        defaults={
                            **serializer.validated_data,
                            "organization": org,
                            "demographics": demographics,
                        },
                    )
                    created += int(new)
                    updated += int(not new)
                except Exception as exc:
                    # Row number only: never print personal fields or raw serializer errors.
                    raise CommandError(f"Rejected row {index + 1}; import rolled back") from exc
            if not options["apply"]:
                transaction.set_rollback(True)
        self.stdout.write(
            json.dumps(
                {
                    "mode": "apply" if options["apply"] else "dry-run",
                    "created": created,
                    "updated": updated,
                    "rows": len(rows),
                }
            )
        )
