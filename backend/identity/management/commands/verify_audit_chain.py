from django.core.management.base import BaseCommand, CommandError

from identity.models import AuditChainHead, AuditEvent, audit_event_hash


class Command(BaseCommand):
    help = "Verify the append-only audit hash chain and current chain head."

    def handle(self, *args, **options):
        previous = ""
        count = 0
        for event in AuditEvent.objects.order_by("sequence").iterator():
            if event.previous_hash != previous:
                raise CommandError(f"Audit chain predecessor mismatch at event {event.pk}")
            expected = audit_event_hash(event, previous)
            if event.event_hash != expected:
                raise CommandError(f"Audit chain content mismatch at event {event.pk}")
            previous = event.event_hash
            count += 1
        head = AuditChainHead.objects.filter(pk="global").first()
        if head is None or head.event_hash != previous or head.sequence != count:
            raise CommandError("Audit chain head does not match the last event")
        self.stdout.write(self.style.SUCCESS(f"Verified {count} audit events"))
