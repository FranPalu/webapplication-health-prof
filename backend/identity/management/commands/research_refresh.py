import os

import psycopg
from django.core.management.base import BaseCommand, CommandError

from identity.research_archive import refresh


class Command(BaseCommand):
    help = "Refresh the internal aggregate research archive in a separate PostgreSQL database."

    def handle(self, *args, **options):
        dsn = os.environ.get("RESEARCH_DATABASE_DSN")
        if not dsn:
            raise CommandError(
                "Configure RESEARCH_DATABASE_DSN for the separate research database."
            )
        try:
            count, changed = refresh(dsn)
        except ValueError as exc:
            raise CommandError(str(exc)) from None
        except psycopg.Error:
            raise CommandError(
                "Research database refresh failed. Check connection and privileges."
            ) from None
        self.stdout.write(
            f"{'Refreshed' if changed else 'Unchanged'} research archive: {count} cells."
        )
