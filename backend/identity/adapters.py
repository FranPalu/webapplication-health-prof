"""Contracts only: no production identity/registry integration is enabled in M1."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VerifiedIdentity:
    issuer: str
    subject: str
    email: str
    email_verified: bool


class IdentityProvider(Protocol):
    def authorization_url(self, *, state: str, nonce: str, pkce_challenge: str) -> str: ...
    def exchange(
        self, *, code: str, state: str, nonce: str, pkce_verifier: str
    ) -> VerifiedIdentity: ...


@dataclass(frozen=True)
class RegistryResult:
    registered: bool
    source: str
    checked_at: str


class ProfessionalRegistry(Protocol):
    def verify(self, *, register: str, license_number: str) -> RegistryResult: ...
