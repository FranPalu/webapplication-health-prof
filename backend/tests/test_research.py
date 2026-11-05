import os

import psycopg
import pytest
from django.utils import timezone
from psycopg.conninfo import make_conninfo
from test_identity import org_for, patient, signed, user

from identity.models import (
    ClinicalObservation,
    ClinicalReport,
    ResearchConsentEvent,
    ResearchTerminology,
)
from identity.research import MIN_PATIENTS, eligible_cells
from identity.research_archive import refresh

pytestmark = pytest.mark.django_db


def test_research_counts_distinct_consented_accounts_and_honors_revocation(settings, monkeypatch):
    ResearchTerminology.objects.create(
        system="loinc",
        code="2345-7",
        version="test",
        source="https://loinc.org/2345-7/",
        license="https://loinc.org/license/",
    )
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
        monkeypatch.setenv("RESEARCH_READ_DSN", dsn)
        settings.RESEARCH_EXPORT_ENABLED = True
        administrator = user("research-requester@patients.example", "organization_admin")
        research_org = org_for(administrator, "Research test")
        research_org.kind = "research"
        research_org.save(update_fields=["kind"])
        researcher = signed(administrator)
        request = researcher.post(
            f"organizations/{research_org.pk}/research/requests/",
            {
                "purpose": "Synthetic aggregate validation",
            },
        )
        assert request.status_code == 201, request.content
        request_id = request.data["id"]
        export = f"research/requests/{request_id}/export/"
        assert researcher.post(export, {"format_name": "csv"}).status_code == 404
        platform = signed(user("research-platform@patients.example", staff=True))
        approved = platform.post(
            f"research/admin/requests/{request_id}/decision/",
            {
                "decision": "approve",
            },
        )
        assert approved.status_code == 200, approved.content
        assert browser.post(export, {"format_name": "csv"}).status_code == 403
        csv = researcher.post(export, {"format_name": "csv"})
        assert csv.status_code == 200 and b"2345-7,10" in csv.content
        parquet = researcher.post(export, {"format_name": "parquet"})
        assert parquet.status_code == 200 and parquet.content.startswith(b"PAR1")
        fhir = researcher.post(export, {"format_name": "fhir"})
        assert fhir.status_code == 200 and fhir.json()["entry"][0]["resource"]["type"] == "summary"
        assert (
            researcher.post(export, {"format_name": "dashboard"}).data["cells"][0]["accounts"] == 10
        )

    if dsn:
        added = user("research-extra@patients.example")
        extra = patient(org)
        extra.account = added
        extra.save(update_fields=["account"])
        report = ClinicalReport.objects.create(
            patient=extra,
            author=author,
            code="24323-8",
            title="Synthetic",
            effective_at=timezone.now(),
        )
        ClinicalObservation.objects.create(
            report=report,
            code="2345-7",
            label="Synthetic",
            value=90,
            unit="mg/dL",
        )
        ResearchConsentEvent.objects.create(patient=extra, actor=added, version=1, granted=True)
        assert refresh(dsn) == (1, True)
        assert researcher.post(export, {"format_name": "csv"}).status_code == 409
        ResearchConsentEvent.objects.create(patient=extra, actor=added, version=1, granted=False)
        assert refresh(dsn) == (1, True)

    assert not browser.post(target, {"version": 1, "granted": False}).data["granted"]
    assert list(eligible_cells()) == []
    if dsn:
        assert researcher.post(export, {"format_name": "csv"}).status_code == 409
        assert refresh(dsn) == (0, True)
        assert refresh(dsn) == (0, False)
        with psycopg.connect(dsn) as target, target.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM claria_research_cell")
            assert cursor.fetchone() == (0,)
