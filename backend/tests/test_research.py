import os

import psycopg
import pytest
from django.utils import timezone
from psycopg.conninfo import make_conninfo
from test_identity import org_for, patient, signed, user

from identity.models import ClinicalObservation, ClinicalReport, ResearchConsentEvent
from identity.research import MIN_PATIENTS, eligible_cells
from identity.research_archive import refresh

pytestmark = pytest.mark.django_db


def test_research_counts_distinct_consented_accounts_and_honors_revocation():
    author = user("research-clinician@patients.example", "professional")
    org = org_for(author)
    accounts = [user(f"research-{index}@patients.example") for index in range(MIN_PATIENTS)]
    records = []
    for account in accounts:
        record = patient(org)
        record.account = account
        record.save(update_fields=["account"])
        records.append(record)
        report = ClinicalReport.objects.create(
            patient=record,
            author=author,
            code="24323-8",
            title="Synthetic",
            effective_at=timezone.now(),
        )
        for _ in range(2):
            ClinicalObservation.objects.create(
                report=report,
                code="2345-7",
                label="Synthetic",
                value=90,
                unit="mg/dL",
            )
    for record, account in zip(records[:-1], accounts[:-1], strict=True):
        ResearchConsentEvent.objects.create(patient=record, actor=account, version=1, granted=True)
    assert list(eligible_cells()) == []
    target = f"patients/{records[-1].pk}/research-consent/"
    assert signed(accounts[0]).post(target, {"version": 1, "granted": True}).status_code == 404
    browser = signed(accounts[-1])
    assert browser.post(target, {"version": 2, "granted": True}).status_code == 400
    assert browser.post(target, {"version": 1, "granted": True}).data["granted"]
    (cell,) = eligible_cells()
    assert cell["patients"] == MIN_PATIENTS
    assert set(cell) == {"year", "code", "patients"}
    archive = os.environ.get("RESEARCH_INTEGRATION_DB")
    dsn = None
    if archive:
        dsn = make_conninfo(
            dbname=archive,
            host=os.environ["POSTGRES_HOST"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            port=os.environ.get("POSTGRES_PORT", "5432"),
        )
        assert refresh(dsn) == (1, True)
        assert refresh(dsn) == (1, False)

    assert not browser.post(target, {"version": 1, "granted": False}).data["granted"]
    assert list(eligible_cells()) == []
    if dsn:
        assert refresh(dsn) == (0, True)
        assert refresh(dsn) == (0, False)
        with psycopg.connect(dsn) as target, target.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM claria_research_cell")
            assert cursor.fetchone() == (0,)
