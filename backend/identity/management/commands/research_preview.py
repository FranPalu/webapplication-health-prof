from django.core.management.base import BaseCommand

from identity.research import eligible_cells


class Command(BaseCommand):
    help = "Count publishable research cells without exposing their contents or writing a dataset."

    def handle(self, *args, **options):
        eligible = eligible_cells().count()
        suppressed = eligible_cells(minimum=1).count() - eligible
        self.stdout.write(f"Eligible aggregate cells: {eligible}; suppressed: {suppressed}")
