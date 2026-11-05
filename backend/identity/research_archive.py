"""Write the current fixed aggregate projection to a separate PostgreSQL database."""

import hashlib
import json

import psycopg
from django.db import connection

from identity.research import MIN_PATIENTS, eligible_cells

DATASET = "laboratory-account-counts-v1"
LOCK_ID = 742948381


def snapshot_digest(rows):
    return hashlib.sha256(
        json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def refresh(dsn):
    with connection.cursor() as source:
        source.execute("SELECT current_database()")
        source_name = source.fetchone()[0]
    with psycopg.connect(dsn, connect_timeout=5) as target, target.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        destination = cursor.fetchone()
        if destination is None or destination[0] == source_name:
            raise ValueError("Use a separate research database with a distinct name.")
        cursor.execute("SET LOCAL lock_timeout = '10s'")
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS claria_research_release (
                dataset text PRIMARY KEY,
                checksum char(64) NOT NULL,
                generated_at timestamptz NOT NULL DEFAULT now()
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS claria_research_cell (
                dataset text NOT NULL REFERENCES claria_research_release(dataset),
                year integer NOT NULL,
                code text NOT NULL,
                accounts bigint NOT NULL CHECK (accounts >= {MIN_PATIENTS}),
                PRIMARY KEY (dataset, year, code)
            )
        """)
        rows = list(eligible_cells().values_list("year", "code", "patients"))
        digest = snapshot_digest(rows)
        cursor.execute(
            "SELECT checksum FROM claria_research_release WHERE dataset = %s", (DATASET,)
        )
        previous = cursor.fetchone()
        if previous and previous[0] == digest:
            return len(rows), False
        cursor.execute(
            """
            INSERT INTO claria_research_release (dataset, checksum) VALUES (%s, %s)
            ON CONFLICT (dataset) DO UPDATE
                SET checksum = EXCLUDED.checksum, generated_at = now()
        """,
            (DATASET, digest),
        )
        cursor.execute("DELETE FROM claria_research_cell WHERE dataset = %s", (DATASET,))
        cursor.executemany(
            """
            INSERT INTO claria_research_cell (dataset, year, code, accounts)
            VALUES (%s, %s, %s, %s)
        """,
            [(DATASET, *row) for row in rows],
        )
        return len(rows), True
