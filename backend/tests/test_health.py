import pytest
from django.db import OperationalError


@pytest.mark.django_db
def test_readiness_checks_database_without_login(client):
    response = client.get("/health/ready/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["Cache-Control"] == "no-store"


def test_database_failure_changes_readiness_but_not_liveness(client, monkeypatch):
    def fail():
        raise OperationalError("internal database details")

    monkeypatch.setattr("config.health.connection.cursor", fail)
    response = client.get("/health/ready/")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response["Cache-Control"] == "no-store"
    assert client.get("/health/").status_code == 200
