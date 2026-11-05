"""Clinical document policy, scanner and authenticated envelope encryption."""

import base64
import hashlib
import hmac
import os
import socket
import struct

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.db.models import Q
from rest_framework.exceptions import APIException, ValidationError

from identity.models import ClinicalDocument, ClinicalFolder
from identity.services import (
    share_is_active,
    share_recipient_queryset,
    verified_professional,
    visible_patients,
)

CLINICAL_CONSENT_VERSION = 2
MAX_BYTES = 10 * 1024 * 1024


class DocumentUnavailable(APIException):
    status_code = 503
    default_detail = "Clinical document service unavailable."


def clinical_patients(user):
    return visible_patients(user).filter(
        carerelationship__professional=user,
        carerelationship__active=True,
        organization__membership__user=user,
        organization__membership__active=True,
    )


def shared_scopes(user, permission):
    charts, items, folders = [], [], []
    for share in share_recipient_queryset(user).select_related("parent"):
        if permission not in share.permissions or not share_is_active(
            share, CLINICAL_CONSENT_VERSION
        ):
            continue
        if share.scope == "chart":
            charts.append(share.patient_id)
        elif share.document_id:
            items.append(share.document_id)
        elif share.scope == "folder" and share.folder_id:
            folders.append(share.folder_id)
    return charts, items, folders


def descendant_folders(roots):
    seen = set(roots)
    frontier = seen.copy()
    while frontier:
        children = ClinicalFolder.objects.filter(parent_id__in=frontier).values_list(
            "pk", flat=True
        )
        frontier = set(children) - seen
        seen.update(frontier)
    return seen


def visible_documents(user, permission="view"):
    direct = visible_patients(user)
    charts, items, folders = shared_scopes(user, permission)
    authored = Q(pk__in=[])
    if verified_professional(user):
        authored = Q(patient__in=clinical_patients(user), author=user)
    return ClinicalDocument.objects.filter(deleted_at__isnull=True).filter(
        authored
        | (
            ~Q(kind=ClinicalDocument.Kind.PSYCHOLOGY)
            & (
                Q(patient__in=direct)
                | (
                    ~Q(kind=ClinicalDocument.Kind.PRESCRIPTION)
                    & (
                        Q(patient_id__in=charts)
                        | Q(pk__in=items)
                        | Q(folder_id__in=descendant_folders(folders))
                    )
                )
            )
        )
    )


def media_type(data):
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[128:132] == b"DICM":
        return "application/dicom"
    raise ValidationError("Unsupported file signature.")


def scan(data):
    host = os.environ.get("CLINICAL_CLAMAV_HOST")
    if not host:
        raise DocumentUnavailable()
    try:
        with socket.create_connection((host, 3310), timeout=10) as connection:
            connection.sendall(b"zINSTREAM\0")
            for offset in range(0, len(data), 65536):
                chunk = data[offset : offset + 65536]
                connection.sendall(struct.pack("!I", len(chunk)) + chunk)
            connection.sendall(b"\0" * 4)
            with connection.makefile("rb") as stream:
                reply = bytearray()
                while len(reply) < 512:
                    byte = stream.read(1)
                    if byte == b"\0":
                        break
                    if not byte:
                        raise DocumentUnavailable()
                    reply.extend(byte)
                verdict = bytes(reply)
    except OSError as exc:
        raise DocumentUnavailable() from exc
    if verdict == b"stream: OK":
        return
    if verdict.endswith(b" FOUND"):
        raise ValidationError("File rejected by malware scanner.")
    raise DocumentUnavailable()


def tenant_cipher(organization_id):
    keys = [settings.CLINICAL_MASTER_KEY]
    keys.extend(filter(None, os.environ.get("CLINICAL_PREVIOUS_MASTER_KEYS", "").split(",")))
    ciphers = []
    for encoded in keys:
        try:
            master = base64.b64decode(encoded, altchars=b"-_", validate=True)
        except ValueError as exc:
            raise DocumentUnavailable() from exc
        if len(master) != 32:
            raise DocumentUnavailable()
        tenant_key = hmac.digest(master, f"claria-clinical-v1:{organization_id}".encode(), "sha256")
        ciphers.append(Fernet(base64.urlsafe_b64encode(tenant_key)))
    return MultiFernet(ciphers)


def search_tokens(text, organization_id):
    from identity.clinical_formats import terms

    key = os.environ.get("CLINICAL_SEARCH_KEY", "")
    if not key:
        return []
    tenant_key = hmac.digest(key.encode(), str(organization_id).encode(), "sha256")
    return sorted(hmac.digest(tenant_key, word.encode(), "sha256").hex() for word in terms(text))


def seal(data, organization_id):
    from identity.clinical_storage import wrap_key

    key = Fernet.generate_key()
    key_id, wrapped = wrap_key(key, organization_id)
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "wrapped_key": wrapped,
        "key_id": key_id,
        "ciphertext": Fernet(key).encrypt(data),
    }
