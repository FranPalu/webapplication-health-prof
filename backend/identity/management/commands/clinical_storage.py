from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from identity.clinical_storage import maintain_version, read_content
from identity.models import ClinicalDocument, ClinicalDocumentVersion
from identity.security import audit


class Command(BaseCommand):
    help = "Reconcile, verify, rotate keys or purge archived clinical document versions."

    def add_arguments(self, parser):
        parser.add_argument(
            "operation", choices=["offload", "verify", "rotate", "purge", "hold", "release-hold"]
        )
        parser.add_argument("--tenant")
        parser.add_argument("--days", type=int)
        parser.add_argument("--document")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        operation = options["operation"]
        if operation in ("hold", "release-hold"):
            self.set_hold(options, operation == "hold")
            return
        versions = ClinicalDocumentVersion.objects.filter(purged_at__isnull=True)
        if options["tenant"]:
            versions = versions.filter(document__patient__organization_id=options["tenant"])
        cutoff = None
        if operation == "purge":
            if not options["tenant"] or not options["days"] or options["days"] < 1:
                raise CommandError("Purge requires an explicit tenant and positive retention days.")
            cutoff = timezone.now() - timedelta(days=options["days"])
            versions = versions.filter(
                document__deleted_at__lte=cutoff, document__retention_hold=False
            )
        if operation == "offload":
            versions = versions.filter(object_key="")
        if operation in ("purge", "rotate") and not options["apply"]:
            self.stdout.write(f"Dry run: {versions.count()} candidate versions.")
            return
        processed = 0
        for version_id in versions.values_list("pk", flat=True).iterator(chunk_size=100):
            try:
                if operation == "verify":
                    version = ClinicalDocumentVersion.objects.select_related(
                        "document__patient"
                    ).get(pk=version_id)
                    read_content(version)
                else:
                    maintain_version(version_id, cutoff=cutoff, rotate=operation == "rotate")
            except Exception:
                raise CommandError(
                    f"Stopped after {processed} versions. Inspect storage and key configuration."
                ) from None
            processed += 1
        self.stdout.write(f"Processed {processed} versions.")

    @transaction.atomic
    def set_hold(self, options, hold):
        if not options["tenant"] or not options["document"]:
            raise CommandError("Specify both --tenant and --document.")
        try:
            document = ClinicalDocument.objects.select_for_update().get(
                pk=options["document"], patient__organization_id=options["tenant"]
            )
        except ClinicalDocument.DoesNotExist:
            raise CommandError("Document not found in tenant.") from None
        if options["apply"]:
            document.retention_hold = hold
            document.save(update_fields=["retention_hold"])
            event = "clinical.hold_set" if hold else "clinical.hold_released"
            audit(None, event, document.pk, document.patient.organization)
        self.stdout.write("Hold updated." if options["apply"] else "Dry run: one document.")
