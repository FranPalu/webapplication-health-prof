"""Every national connector is an explicit test double, not an active provider."""

from dataclasses import replace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from identity.interop_adapters import OPERATIONS, IntegrationReceipt, IntegrationRequest, dispatch
from identity.interop_oauth import IntegrationUnavailable


@pytest.mark.parametrize("service", sorted(OPERATIONS))
def test_national_adapter_contracts_bind_receipts_and_disable_missing_provider(service):
    organization, key = uuid4(), uuid4()
    operation = next(
        operation
        for operation in sorted(OPERATIONS[service])
        if operation != "publish_signed_document"
    )
    request = IntegrationRequest(
        organization, service, operation, b"SYNTHETIC TEST PAYLOAD", key, "administration", uuid4()
    )
    request = replace(request, signed_document_sha256=request.payload_sha256)
    provider = Mock()
    provider.execute.return_value = IntegrationReceipt(
        organization, key, request.payload_sha256, "SYNTHETIC-ONLY", "validated"
    )
    assert (
        dispatch(
            request,
            {service: provider},
            permitted_organization=organization,
            enabled_services=frozenset({service}),
        ).status
        == "validated"
    )
    with pytest.raises(IntegrationUnavailable):
        dispatch(
            request, {}, permitted_organization=organization, enabled_services=frozenset({service})
        )
    with pytest.raises(PermissionError):
        dispatch(
            request,
            {service: provider},
            permitted_organization=uuid4(),
            enabled_services=frozenset({service}),
        )
    with pytest.raises(PermissionError):
        dispatch(
            replace(request, operation="unsupported"),
            {service: provider},
            permitted_organization=organization,
            enabled_services=frozenset({service}),
        )
    provider.execute.return_value = replace(provider.execute.return_value, payload_sha256="0" * 64)
    with pytest.raises(ValueError):
        dispatch(
            request,
            {service: provider},
            permitted_organization=organization,
            enabled_services=frozenset({service}),
        )


def test_fse_publication_requires_exact_verified_signed_document_digest():
    organization = uuid4()
    request = IntegrationRequest(
        organization,
        "fse",
        "publish_signed_document",
        b"SYNTHETIC UNSIGNED",
        uuid4(),
        "care",
        uuid4(),
    )
    with pytest.raises(PermissionError):
        dispatch(
            request,
            {"fse": Mock()},
            permitted_organization=organization,
            enabled_services=frozenset({"fse"}),
        )


def test_signed_digest_alone_cannot_authorize_fse_publication():
    from identity.interop_adapters import VerifiedPublication

    organization = uuid4()
    request = IntegrationRequest(
        organization, "fse", "publish_signed_document", b"SYNTHETIC", uuid4(), "care", uuid4()
    )
    request = replace(request, signed_document_sha256=request.payload_sha256)
    adapter = Mock()
    adapter.execute.return_value = IntegrationReceipt(
        organization, request.idempotency_key, request.payload_sha256, "SYNTHETIC-ONLY", "submitted"
    )
    with pytest.raises(PermissionError):
        dispatch(
            request,
            {"fse": adapter},
            permitted_organization=organization,
            enabled_services=frozenset({"fse"}),
        )
    verifier = Mock()
    verifier.verify.return_value = VerifiedPublication(uuid4(), uuid4(), request.payload_sha256)
    with pytest.raises(PermissionError):
        dispatch(
            request,
            {"fse": adapter},
            permitted_organization=organization,
            enabled_services=frozenset({"fse"}),
            signature_verifier=verifier,
        )
    verifier.verify.return_value = VerifiedPublication(
        organization, uuid4(), request.payload_sha256
    )
    assert (
        dispatch(
            request,
            {"fse": adapter},
            permitted_organization=organization,
            enabled_services=frozenset({"fse"}),
            signature_verifier=verifier,
        ).status
        == "submitted"
    )
