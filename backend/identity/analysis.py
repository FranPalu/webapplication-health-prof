"""Clinical analysis access policy and tenant-bound encrypted payloads."""

import json
from dataclasses import dataclass

from cryptography.fernet import Fernet
from django.conf import settings

from identity.clinical import clinical_patients, seal
from identity.clinical_storage import unwrap_key
from identity.models import (
    AnalysisJob,
    CareRelationship,
    ClinicalDocument,
    ClinicalDocumentVersion,
    Membership,
    ProfessionalVerification,
    User,
)
from identity.services import verified_professional


def enabled():
    return settings.DEBUG and settings.CLINICAL_ANALYSIS_ENABLED


def eligible(user):
    return (
        user.is_active and user.email_verified and user.mfa_enabled and verified_professional(user)
    )


def authorized_jobs(user):
    if not enabled() or not eligible(user):
        return AnalysisJob.objects.none()
    return AnalysisJob.objects.filter(
        version__document__patient__in=clinical_patients(user),
        version__document__deleted_at__isnull=True,
        version__purged_at__isnull=True,
    )


def requester_allowed(job, *, lock=False):
    user = job.requested_by
    if lock:
        user = User.objects.select_for_update().get(pk=job.requested_by_id)
        version = (
            ClinicalDocumentVersion.objects.select_for_update()
            .only("document_id")
            .get(pk=job.version_id)
        )
        document = ClinicalDocument.objects.select_for_update().get(pk=version.document_id)
        Membership.objects.select_for_update().filter(
            user=user, organization_id=document.patient.organization_id
        ).first()
        CareRelationship.objects.select_for_update().filter(
            patient_id=document.patient_id, professional=user
        ).first()
        ProfessionalVerification.objects.select_for_update().filter(user=user).first()
    return (
        user.auth_version == job.auth_version and authorized_jobs(user).filter(pk=job.pk).exists()
    )


def encode(value, tenant):
    return seal(json.dumps(value, ensure_ascii=False, sort_keys=True).encode(), tenant)


@dataclass
class PayloadKey:
    document: ClinicalDocument
    wrapped_key: bytes
    key_id: str


def decode(payload, document):
    key = unwrap_key(PayloadKey(document, bytes(payload.wrapped_key), payload.key_id))
    return json.loads(Fernet(key).decrypt(bytes(payload.ciphertext)))
