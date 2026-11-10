"""Internal versioned contracts only, not national wire-protocol implementations.

No default adapter, fabricated endpoint, automatic publication or credential is
provided. Deployment adapters must implement the actual accredited protocols.
"""

import hashlib
from dataclasses import dataclass
from typing import Literal, Mapping, Protocol
from uuid import UUID

from identity.interop_oauth import IntegrationUnavailable

Service = Literal["fse", "eds", "nre", "ts", "ana", "anpr", "spid", "cie", "pagopa", "sdi"]
OPERATIONS = {
    "fse": frozenset({"validate_document", "publish_signed_document"}),
    "eds": frozenset({"validate_dataset"}),
    "nre": frozenset({"verify_prescription"}),
    "ts": frozenset({"validate_health_expense"}),
    "ana": frozenset({"verify_identity"}),
    "anpr": frozenset({"verify_identity"}),
    "spid": frozenset({"begin_authorization", "verify_callback"}),
    "cie": frozenset({"begin_authorization", "verify_callback"}),
    "pagopa": frozenset({"create_payment_notice", "verify_receipt"}),
    "sdi": frozenset({"validate_invoice", "submit_invoice"}),
}
CONTRACT_VERSION = "claria-national-adapter-v1"


@dataclass(frozen=True)
class IntegrationRequest:
    organization_id: UUID
    service: Service
    operation: str
    payload: bytes
    idempotency_key: UUID
    purpose: Literal["care", "administration", "identity"]
    authorization_reference: UUID
    signed_document_sha256: str = ""

    @property
    def payload_sha256(self):
        return hashlib.sha256(self.payload).hexdigest()


@dataclass(frozen=True)
class IntegrationReceipt:
    organization_id: UUID
    idempotency_key: UUID
    payload_sha256: str
    external_reference: str
    status: Literal["validated", "submitted", "rejected"]
    contract_version: str = CONTRACT_VERSION


class NationalAdapter(Protocol):
    """Adapter must never treat a timeout or submission as clinical acceptance."""

    def execute(self, request: IntegrationRequest) -> IntegrationReceipt: ...


@dataclass(frozen=True)
class VerifiedPublication:
    organization_id: UUID
    signer_id: UUID
    payload_sha256: str


class SignedDocumentVerifier(Protocol):
    def verify(self, payload: bytes, organization_id: UUID) -> VerifiedPublication: ...


def dispatch(
    request: IntegrationRequest,
    adapters: Mapping[str, NationalAdapter],
    *,
    permitted_organization: UUID,
    enabled_services: frozenset[str],
    signature_verifier: SignedDocumentVerifier | None = None,
) -> IntegrationReceipt:
    if (
        request.organization_id != permitted_organization
        or request.service not in enabled_services
        or request.operation not in OPERATIONS.get(request.service, ())
        or not request.authorization_reference
        or not isinstance(request.payload, bytes)
        or not 0 < len(request.payload) <= 10 * 1024 * 1024
    ):
        raise PermissionError("Integration context not authorized.")
    if (
        request.operation == "publish_signed_document"
        and request.signed_document_sha256 != request.payload_sha256
    ):
        raise PermissionError("The exact signed document must be verified before publication.")
    if request.operation == "publish_signed_document":
        if signature_verifier is None:
            raise PermissionError("An independent trusted signature verifier is required.")
        proof = signature_verifier.verify(request.payload, request.organization_id)
        if (
            proof.organization_id != request.organization_id
            or proof.payload_sha256 != request.payload_sha256
            or not proof.signer_id
        ):
            raise PermissionError("Signature proof does not bind this document and organization.")
    adapter = adapters.get(request.service)
    if adapter is None:
        raise IntegrationUnavailable()
    receipt = adapter.execute(request)
    if (
        receipt.contract_version != CONTRACT_VERSION
        or receipt.organization_id != request.organization_id
        or receipt.idempotency_key != request.idempotency_key
        or receipt.payload_sha256 != request.payload_sha256
        or receipt.status not in ("validated", "submitted", "rejected")
        or not receipt.external_reference
        or len(receipt.external_reference) > 160
    ):
        raise ValueError("Unbound or invalid integration receipt.")
    return receipt
