from datetime import date

import pytest
from rest_framework.exceptions import ValidationError

from identity.patient_identification import (
    IdentificationUnavailable,
    fiscal_birth_matches,
    identifier_digest,
    normalized_identifier,
)


def test_normalization_and_checksum_with_synthetic_fiscal_codes():
    assert normalized_identifier("facility", " syn-1 ") == "SYN-1"
    assert normalized_identifier("health_card", "0" * 20) == "0" * 20
    assert fiscal_birth_matches("ZZZZZZ90A01Z999I", date(1990, 1, 1))
    assert fiscal_birth_matches("ZZZZZZVLA41Z999M", date(1990, 1, 1))
    assert not fiscal_birth_matches("ZZZZZZ90A01Z999I", date(1990, 1, 2))
    for kind, value in (
        ("facility", "ß"),
        ("facility", "abc!"),
        ("health_card", "X" * 20),
        ("tax_code", "ZZZZZZ90A01Z999A"),
    ):
        with pytest.raises(ValidationError):
            normalized_identifier(kind, value)


def test_identity_hmac_separates_tenants_and_fails_closed(settings):
    settings.CLINICAL_IDENTITY_KEY = ""
    with pytest.raises(IdentificationUnavailable):
        identifier_digest("tenant-one", "facility", "synthetic")
    settings.CLINICAL_IDENTITY_KEY = "synthetic-only-" * 4
    first = identifier_digest("tenant-one", "facility", "synthetic")
    assert first == identifier_digest("tenant-one", "facility", "SYNTHETIC")
    assert first != identifier_digest("tenant-two", "facility", "synthetic")
