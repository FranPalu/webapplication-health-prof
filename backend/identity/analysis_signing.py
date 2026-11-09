"""Clinical signature verification boundary. No production verifier is bundled."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from django.conf import settings
from django.utils.module_loading import import_string
from rest_framework.exceptions import APIException, ValidationError


class InvalidClinicalSignature(ValidationError):
    default_detail = "The signed artifact could not be verified."


class SignatureUnavailable(APIException):
    status_code = 503
    default_detail = "Clinical signature verification is unavailable."


@dataclass(frozen=True)
class VerifiedClinicalSignature:
    signer_id: UUID
    digest: str
    signed_at: datetime
    provider_reference: str
    format: str


class ClinicalSignatureVerifier(Protocol):
    def verify(
        self, *, artifact: bytes, expected_digest: str, expected_signer_id: UUID
    ) -> VerifiedClinicalSignature: ...


def verifier() -> ClinicalSignatureVerifier:
    path = settings.CLINICAL_SIGNATURE_VERIFIER
    if not path:
        raise SignatureUnavailable()
    return import_string(path)()


def signing_content(job, review, text):
    """Canonical UTF-8 manifest signed by the external trusted verifier/provider."""
    return json.dumps(
        {
            "schema": "claria-reviewed-opinion-v1",
            "job": str(job.pk),
            "source_sha256": job.input_hash,
            "author": str(review.author_id),
            "reviewed_at": review.created_at.isoformat(),
            "text": text,
            "purpose": "Professional reviewed opinion, distinct from AI draft",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
