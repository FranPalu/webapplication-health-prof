"""Durable staging and private S3 storage for encrypted clinical versions."""

import hashlib
import os

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from identity.clinical import MAX_BYTES, DocumentUnavailable, tenant_cipher
from identity.models import (
    AnalysisDraft,
    AnalysisIncident,
    AnalysisOpinion,
    AnalysisReview,
    AnalysisSignature,
    ClinicalDocumentVersion,
)
from identity.security import audit


def aws(service):
    options = {
        "region_name": os.environ.get("S3_REGION", "eu-west-1"),
        "config": Config(connect_timeout=3, read_timeout=8, retries={"total_max_attempts": 2}),
    }
    if service == "s3" and os.environ.get("S3_ENDPOINT"):
        options.update(
            endpoint_url=os.environ["S3_ENDPOINT"],
            aws_access_key_id=os.environ.get("S3_ACCESS_KEY"),
            aws_secret_access_key=os.environ.get("S3_SECRET_KEY"),
        )
    return boto3.client(service, **options)


def bucket():
    name = os.environ.get("S3_BUCKET")
    if not name:
        raise DocumentUnavailable()
    return name


def wrap_key(key, organization_id):
    key_id = os.environ.get("CLINICAL_KMS_KEY_ID", "")
    if not key_id:
        if not settings.DEBUG:
            raise DocumentUnavailable()
        return "", tenant_cipher(organization_id).encrypt(key)
    try:
        result = aws("kms").encrypt(
            KeyId=key_id, Plaintext=key, EncryptionContext={"tenant": str(organization_id)}
        )
    except (BotoCoreError, ClientError) as exc:
        raise DocumentUnavailable() from exc
    return result["KeyId"], result["CiphertextBlob"]


def unwrap_key(version):
    organization_id = version.document.patient.organization_id
    if not version.key_id:
        return tenant_cipher(organization_id).decrypt(bytes(version.wrapped_key))
    return aws("kms").decrypt(
        KeyId=version.key_id,
        CiphertextBlob=bytes(version.wrapped_key),
        EncryptionContext={"tenant": str(organization_id)},
    )["Plaintext"]


def read_content(version):
    try:
        encrypted = bytes(version.ciphertext)
        if version.object_key:
            response = aws("s3").get_object(Bucket=bucket(), Key=version.object_key)
            with response["Body"] as body:
                encrypted = body.read(2 * MAX_BYTES)
        plaintext = Fernet(unwrap_key(version)).decrypt(encrypted)
        if (
            len(plaintext) != version.size
            or hashlib.sha256(plaintext).hexdigest() != version.sha256
        ):
            raise DocumentUnavailable()
        return plaintext
    except (BotoCoreError, ClientError, InvalidToken) as exc:
        raise DocumentUnavailable() from exc


@transaction.atomic
def offload(version_id):
    version = (
        ClinicalDocumentVersion.objects.select_for_update(of=("self",))
        .select_related("document__patient")
        .get(pk=version_id)
    )
    if version.object_key or version.purged_at:
        return
    key = f"clinical/{version.document.patient.organization_id}/{version.pk}"
    aws("s3").put_object(
        Bucket=bucket(),
        Key=key,
        Body=bytes(version.ciphertext),
        ContentType="application/octet-stream",
    )
    version.object_key = key
    version.ciphertext = b""
    version.save(update_fields=["object_key", "ciphertext"])


def delete_object(key):
    client = aws("s3")
    name = bucket()
    state = client.get_bucket_versioning(Bucket=name).get("Status")
    if state in ("Enabled", "Suspended"):
        pages = client.get_paginator("list_object_versions").paginate(Bucket=name, Prefix=key)
        for page in pages:
            for entry in page.get("Versions", []) + page.get("DeleteMarkers", []):
                if entry["Key"] == key:
                    client.delete_object(Bucket=name, Key=key, VersionId=entry["VersionId"])
    else:
        client.delete_object(Bucket=name, Key=key)


@transaction.atomic
def maintain_version(version_id, *, cutoff=None, rotate=False):
    version = (
        ClinicalDocumentVersion.objects.select_for_update(of=("self", "document"))
        .select_related("document__patient__organization")
        .get(pk=version_id)
    )
    if version.purged_at:
        return
    organization = version.document.patient.organization
    if cutoff:
        if (
            version.document.retention_hold
            or not version.document.deleted_at
            or version.document.deleted_at > cutoff
        ):
            return
        key = version.object_key or f"clinical/{organization.pk}/{version.pk}"
        delete_object(key)
        version.purged_at = timezone.now()
        version.wrapped_key = version.ciphertext = b""
        version.title = ""
        version.search_tokens = []
        version.save(
            update_fields=["purged_at", "wrapped_key", "ciphertext", "title", "search_tokens"]
        )
        AnalysisDraft.objects.filter(job__version=version).update(ciphertext=b"", wrapped_key=b"")
        AnalysisReview.objects.filter(job__version=version).update(ciphertext=b"", wrapped_key=b"")
        AnalysisOpinion.objects.filter(review__job__version=version).update(
            ciphertext=b"", wrapped_key=b""
        )
        AnalysisSignature.objects.filter(opinion__review__job__version=version).update(
            ciphertext=b"", wrapped_key=b""
        )
        AnalysisIncident.objects.filter(job__version=version).update(
            ciphertext=b"", wrapped_key=b""
        )
        audit(None, "clinical.purged", version.pk, organization)
    elif rotate:
        key = unwrap_key(version)
        version.key_id, version.wrapped_key = wrap_key(key, organization.pk)
        version.save(update_fields=["key_id", "wrapped_key"])
        audit(None, "clinical.key_rotated", version.pk, organization)
    else:
        offload(version.pk)
