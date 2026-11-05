from typing import Protocol


class PrescriptionVerifier(Protocol):
    def verified(
        self, *, reference: str, requester_id: str, pharmacy_id: str, sku: str
    ) -> bool: ...


# Official integrations must bind the reference to the patient, pharmacy and item.
verifier: PrescriptionVerifier | None = None
