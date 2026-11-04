"""Clinical document policy, scanner and authenticated envelope encryption."""

import base64
import hashlib
import hmac
import os
import socket
import struct

from cryptography.fernet import Fernet
from django.conf import settings
from django.db.models import Q
from rest_framework.exceptions import APIException, ValidationError

from identity.models import ClinicalDocument
from identity.services import (
    share_is_active,
    share_recipient_queryset,
    verified_professional,
    visible_patients,
)

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


def visible_documents(user, permission="view"):
    direct = visible_patients(user)
    shared = [
        share.patient_id
        for share in share_recipient_queryset(user).filter(scope="chart").select_related("parent")
        if permission in share.permissions and share_is_active(share)
    ]
    authored = Q(pk__in=[])
    if verified_professional(user):
        authored = Q(patient__in=clinical_patients(user), author=user)
    return ClinicalDocument.objects.filter(deleted_at__isnull=True).filter(
        authored
        | (
            ~Q(kind=ClinicalDocument.Kind.PSYCHOLOGY)
            & (Q(patient__in=direct) | Q(patient_id__in=shared))
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
                verdict = stream.read(512).split(b"\0", 1)[0]
    except OSError as exc:
        raise DocumentUnavailable() from exc
    if verdict == b"stream: OK":
        return
    if verdict.endswith(b" FOUND"):
        raise ValidationError("File rejected by malware scanner.")
    raise DocumentUnavailable()


def tenant_cipher(organization_id):
    try:
        master = base64.b64decode(settings.CLINICAL_MASTER_KEY, altchars=b"-_", validate=True)
    except ValueError as exc:
        raise DocumentUnavailable() from exc
    if len(master) != 32:
        raise DocumentUnavailable()
    tenant_key = hmac.digest(master, f"claria-clinical-v1:{organization_id}".encode(), "sha256")
    return Fernet(base64.urlsafe_b64encode(tenant_key))


def seal(data, organization_id):
    key = Fernet.generate_key()
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "wrapped_key": tenant_cipher(organization_id).encrypt(key),
        "ciphertext": Fernet(key).encrypt(data),
    }
