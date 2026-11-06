import hashlib
import json
import uuid
from typing import ClassVar

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models, transaction
from django.db.models.functions import Lower
from django.utils import timezone


def audit_event_hash(event, previous_hash: str) -> str:
    payload = {
        "id": str(event.pk),
        "sequence": event.sequence,
        "actor": str(event.actor_id or ""),
        "organization": str(event.organization_id or ""),
        "action": event.action,
        "resource_id": event.resource_id,
        "at": event.at.isoformat(),
        "previous_hash": previous_hash,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class UserManager(DjangoUserManager["User"]):
    def create_user(self, email, password=None, **extra_fields):  # type: ignore[override]  # Email-only user model.
        user = self.model(email=email.strip().lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        UserProfile.objects.get_or_create(user=user, role=user.role)
        return user

    def create_superuser(self, email, password=None, **extra_fields):  # type: ignore[override]  # Email-only user model.
        return self.create_user(
            email, password, is_staff=True, is_superuser=True, email_verified=True, **extra_fields
        )


class User(AbstractUser):
    username = None  # type: ignore[assignment]  # Email replaces the inherited username field.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(default=False)
    role = models.CharField(
        max_length=24,
        choices=[
            ("patient", "Patient"),
            ("professional", "Professional"),
            ("researcher", "Researcher"),
            ("organization_admin", "Organization admin"),
        ],
    )
    locale = models.CharField(
        max_length=2, choices=[("it", "Italiano"), ("en", "English")], default="it"
    )
    mfa_secret = models.TextField(blank=True)
    mfa_enabled = models.BooleanField(default=False)
    mfa_last_step = models.BigIntegerField(default=-1)
    auth_version = models.PositiveIntegerField(default=1)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []
    objects: ClassVar[UserManager] = UserManager()

    class Meta:
        constraints = [models.UniqueConstraint(Lower("email"), name="user_email_casefold_unique")]

    def has_profile(self, role: str) -> bool:
        return self.role == role or UserProfile.objects.filter(user=self, role=role).exists()

    @property
    def requires_mfa(self) -> bool:
        return (
            self.is_staff
            or self.has_profile("professional")
            or self.has_profile("organization_admin")
            or self.mfa_enabled
            or Membership.objects.filter(user=self, role="admin", active=True).exists()
        )


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    kind = models.CharField(
        max_length=20,
        choices=[(x, x) for x in ("hospital", "clinic", "practice", "pharmacy", "research")],
    )
    break_glass_enabled = models.BooleanField(default=False)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Membership(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    role = models.CharField(
        max_length=20,
        choices=[
            ("admin", "Admin"),
            ("professional", "Professional"),
            ("researcher", "Researcher"),
        ],
    )
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "user"], name="unique_membership")
        ]


class ProfessionalVerification(models.Model):
    user = models.OneToOneField(User, on_delete=models.PROTECT)
    register = models.CharField(max_length=200)
    license_number = models.CharField(max_length=100)
    status = models.CharField(
        max_length=16,
        default="pending",
        choices=[(x, x) for x in ("pending", "approved", "rejected")],
    )
    reviewed_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, related_name="reviews"
    )
    reviewed_at = models.DateTimeField(null=True)
    reason = models.CharField(max_length=500, blank=True)


class Patient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    account = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    birth_date = models.DateField()
    email = models.EmailField(blank=True)
    legacy_source = models.CharField(max_length=100, blank=True)
    legacy_owner = models.CharField(max_length=200, blank=True)
    legacy_id = models.CharField(max_length=200, blank=True)
    demographics = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["legacy_source", "legacy_owner", "legacy_id"],
                condition=~models.Q(legacy_source=""),
                name="unique_imported_patient",
            )
        ]


class PatientIdentifier(models.Model):
    class Kind(models.TextChoices):
        FACILITY = "facility", "Facility identifier"
        TAX_CODE = "tax_code", "Italian tax code"
        HEALTH_CARD = "health_card", "Italian health card number"

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    digest = models.CharField(max_length=64)
    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "kind", "digest"], name="unique_tenant_patient_identifier"
            )
        ]


class CareRelationship(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    professional = models.ForeignKey(User, on_delete=models.PROTECT)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "professional"], name="unique_care_relationship"
            )
        ]


class AccountToken(models.Model):
    digest = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    purpose = models.CharField(max_length=30)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True)
    context = models.JSONField(default=dict)


class RecoveryCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    digest = models.CharField(max_length=64)
    used_at = models.DateTimeField(null=True)


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(User, null=True, on_delete=models.PROTECT)
    organization = models.ForeignKey(Organization, null=True, on_delete=models.PROTECT)
    action = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=100, blank=True)
    at = models.DateTimeField(default=timezone.now)
    previous_hash = models.CharField(max_length=64, blank=True)
    event_hash = models.CharField(max_length=64, blank=True)
    sequence = models.PositiveBigIntegerField(default=0)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            return super().save(*args, **kwargs)
        with transaction.atomic():
            head, _ = AuditChainHead.objects.select_for_update().get_or_create(key="global")
            self.at = self.at or timezone.now()
            self.previous_hash = head.event_hash
            head.sequence += 1
            self.sequence = head.sequence
            self.event_hash = audit_event_hash(self, self.previous_hash)
            super().save(*args, **kwargs)
            head.event_hash = self.event_hash
            head.save(update_fields=["event_hash", "sequence"])


class AuditChainHead(models.Model):
    key = models.CharField(max_length=20, primary_key=True)
    event_hash = models.CharField(max_length=64, blank=True)
    sequence = models.PositiveBigIntegerField(default=0)


class ConsentTextVersion(models.Model):
    purpose = models.CharField(max_length=40)
    version = models.PositiveIntegerField()
    locale = models.CharField(max_length=2)
    text = models.TextField()
    content_hash = models.CharField(max_length=64)
    published_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["purpose", "version", "locale"], name="unique_consent_text_version"
            )
        ]


class PatientConsent(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="consents")
    share = models.ForeignKey(
        "Share", null=True, blank=True, on_delete=models.PROTECT, related_name="consent_events"
    )
    text_version = models.ForeignKey(ConsentTextVersion, on_delete=models.PROTECT)
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    decision = models.CharField(
        max_length=12, choices=[("granted", "Granted"), ("revoked", "Revoked")]
    )
    created_at = models.DateTimeField(default=timezone.now)


class Share(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="shares")
    granted_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="shares_created")
    recipient_user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="shares_received"
    )
    recipient_organization = models.ForeignKey(
        Organization,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="shares_received",
    )
    document = models.ForeignKey(
        "ClinicalDocument", null=True, blank=True, on_delete=models.PROTECT
    )
    folder = models.ForeignKey("ClinicalFolder", null=True, blank=True, on_delete=models.PROTECT)
    scope = models.CharField(
        max_length=12, choices=[("item", "Item"), ("folder", "Folder"), ("chart", "Chart")]
    )
    permissions = models.JSONField(default=list)
    purpose = models.CharField(max_length=300)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(recipient_user__isnull=False, recipient_organization__isnull=True)
                    | models.Q(recipient_user__isnull=True, recipient_organization__isnull=False)
                ),
                name="share_exactly_one_recipient",
            )
        ]


class SecureMessage(models.Model):
    share = models.ForeignKey(Share, on_delete=models.PROTECT, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.PROTECT)
    body = models.TextField(max_length=5000)
    created_at = models.DateTimeField(default=timezone.now)


class InAppNotification(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="notifications")
    category = models.CharField(max_length=32)
    resource_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)


class BreakGlassAccess(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    professional = models.ForeignKey(User, on_delete=models.PROTECT)
    reason = models.CharField(max_length=1000)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    reviewed_at = models.DateTimeField(null=True, blank=True)


class RateBucket(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()


class UserProfile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=24, choices=User._meta.get_field("role").choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "role"], name="unique_user_profile")]


class ClinicalFolder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    title = models.CharField(max_length=100)


class ClinicalDocument(models.Model):
    class Kind(models.TextChoices):
        REPORT = "report", "Referto"
        PRESCRIPTION = "prescription", "Ricetta"
        NUTRITION = "nutrition", "Piano alimentare"
        PSYCHOLOGY = "psychology", "Nota psicologica"
        OTHER = "other", "Altro"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    author = models.ForeignKey(User, on_delete=models.PROTECT)
    folder = models.ForeignKey(ClinicalFolder, null=True, blank=True, on_delete=models.PROTECT)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    deleted_at = models.DateTimeField(null=True)
    retention_hold = models.BooleanField(default=False)


class ClinicalDocumentVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        ClinicalDocument, on_delete=models.PROTECT, related_name="versions"
    )
    number = models.PositiveIntegerField()
    title = models.CharField(max_length=160)
    media_type = models.CharField(max_length=40)
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    wrapped_key = models.BinaryField()
    ciphertext = models.BinaryField()
    object_key = models.CharField(max_length=160, blank=True)
    key_id = models.CharField(max_length=255, blank=True)
    purged_at = models.DateTimeField(null=True)
    search_tokens = models.JSONField(default=list)
    offload_after = models.DateTimeField(default=timezone.now)
    offload_failures = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "number"], name="clinical_document_version")
        ]


class ClinicalEncounter(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    author = models.ForeignKey(User, on_delete=models.PROTECT)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ended_at__gte=models.F("started_at")),
                name="clinical_encounter_period",
            )
        ]


class ClinicalReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    author = models.ForeignKey(User, on_delete=models.PROTECT)
    encounter = models.ForeignKey(ClinicalEncounter, null=True, on_delete=models.PROTECT)
    code = models.CharField(max_length=32)
    title = models.CharField(max_length=160)
    effective_at = models.DateTimeField()

    recorded_at = models.DateTimeField(null=True)
    version = models.PositiveIntegerField(default=1)
    root = models.ForeignKey("self", null=True, on_delete=models.PROTECT, related_name="revisions")
    previous = models.OneToOneField(
        "self", null=True, on_delete=models.PROTECT, related_name="superseding_revision"
    )
    correction_reason = models.CharField(max_length=500, blank=True)
    terminology_version = models.CharField(max_length=32, blank=True)
    evaluation_sex = models.CharField(max_length=6, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["root", "version"], name="unique_report_revision"),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        version=1, root__isnull=True, previous__isnull=True, correction_reason=""
                    )
                    | (
                        models.Q(
                            version__gt=1,
                            root__isnull=False,
                            previous__isnull=False,
                            recorded_at__isnull=False,
                        )
                        & ~models.Q(correction_reason="")
                    )
                ),
                name="report_revision_shape",
            ),
        ]


class ClinicalObservation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(
        ClinicalReport, on_delete=models.PROTECT, related_name="observations"
    )
    code = models.CharField(max_length=32)
    label = models.CharField(max_length=160)
    value = models.DecimalField(max_digits=16, decimal_places=6)
    unit = models.CharField(max_length=32)

    reference_range = models.JSONField(default=dict)


class AnalysisModel(models.Model):
    name = models.CharField(max_length=120)
    revision = models.CharField(max_length=120)
    checksum = models.CharField(max_length=64)
    license = models.CharField(max_length=120)
    intended_use = models.TextField()
    limitations = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "revision", "checksum"], name="analysis_model_release"
            )
        ]


class AnalysisJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(ClinicalDocumentVersion, on_delete=models.PROTECT)
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT)
    auth_version = models.PositiveIntegerField()
    pipeline = models.CharField(max_length=64)
    input_hash = models.CharField(max_length=64)
    state = models.CharField(max_length=16, default="queued")
    attempts = models.PositiveSmallIntegerField(default=0)
    lease_until = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["version", "pipeline"], name="analysis_job_dedup")
        ]


class AnalysisPayload(models.Model):
    ciphertext = models.BinaryField()
    wrapped_key = models.BinaryField()
    key_id = models.CharField(max_length=255, blank=True)
    sha256 = models.CharField(max_length=64)

    class Meta:
        abstract = True


class AnalysisDraft(AnalysisPayload):
    job = models.OneToOneField(AnalysisJob, on_delete=models.PROTECT, related_name="draft")
    model = models.ForeignKey(AnalysisModel, null=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class AnalysisReview(AnalysisPayload):
    job = models.OneToOneField(AnalysisJob, on_delete=models.PROTECT, related_name="review")
    author = models.ForeignKey(User, on_delete=models.PROTECT)
    decision = models.CharField(max_length=8)
    created_at = models.DateTimeField(auto_now_add=True)


class AnalysisOpinion(AnalysisPayload):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.OneToOneField(AnalysisReview, on_delete=models.PROTECT, related_name="opinion")
    created_at = models.DateTimeField(auto_now_add=True)
    attestation_hash = models.CharField(max_length=64)


class AnalysisPublication(models.Model):
    recipient = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="analysis_publications_received"
    )
    opinion = models.OneToOneField(AnalysisOpinion, on_delete=models.PROTECT)
    author = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class PaymentPrice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    title = models.CharField(max_length=120)
    amount = models.PositiveIntegerField()
    fee = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)


class PaymentOrder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    price = models.ForeignKey(PaymentPrice, on_delete=models.PROTECT)
    payer = models.ForeignKey(User, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    amount = models.PositiveIntegerField()
    fee = models.PositiveIntegerField()
    destination = models.CharField(max_length=80)
    checkout_session = models.CharField(max_length=200, blank=True)
    simulation_status = models.CharField(max_length=16, default="legacy")
    paid_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["payer", "request_id"], name="payment_order_idempotency"
            )
        ]


class PaymentEvent(models.Model):
    provider_id = models.CharField(max_length=200, unique=True)
    order = models.ForeignKey(PaymentOrder, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class AppointmentSlot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    professional = models.ForeignKey(User, on_delete=models.PROTECT)
    title = models.CharField(max_length=120)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    price = models.ForeignKey(PaymentPrice, null=True, blank=True, on_delete=models.PROTECT)


class AppointmentBooking(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slot = models.ForeignKey(AppointmentSlot, on_delete=models.PROTECT, related_name="bookings")
    payer = models.ForeignKey(User, on_delete=models.PROTECT)
    payment = models.OneToOneField(PaymentOrder, null=True, blank=True, on_delete=models.PROTECT)
    cancelled_at = models.DateTimeField(null=True)
    reminded_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["slot"],
                condition=models.Q(cancelled_at__isnull=True),
                name="appointment_one_active_booking",
            )
        ]


class PharmacyItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pharmacy = models.ForeignKey(Organization, on_delete=models.PROTECT)
    sku = models.CharField(max_length=64)
    title = models.CharField(max_length=120)
    stock = models.PositiveIntegerField()
    prescription_required = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["pharmacy", "sku"], name="pharmacy_unique_sku")
        ]


class PharmacyReservation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(PharmacyItem, on_delete=models.PROTECT)
    requester = models.ForeignKey(User, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    quantity = models.PositiveIntegerField()
    state = models.CharField(max_length=12, default="pending")
    prescription = models.JSONField(null=True)
    prescription_version = models.ForeignKey(
        ClinicalDocumentVersion, null=True, blank=True, on_delete=models.PROTECT
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["requester", "request_id"], name="pharmacy_reservation_idempotency"
            )
        ]


class ResearchConsentEvent(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    version = models.PositiveSmallIntegerField()
    granted = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["patient", "-id"], name="research_consent_latest")]


class ResearchAccessRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    decided_by = models.ForeignKey(User, null=True, on_delete=models.PROTECT, related_name="+")
    purpose = models.CharField(max_length=500)
    status = models.CharField(max_length=16, default="pending")
    checksum = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ResearchReleasedSnapshot(models.Model):
    dataset = models.CharField(max_length=64, primary_key=True)
    checksum = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)


class ResearchTerminology(models.Model):
    system = models.CharField(max_length=16)
    code = models.CharField(max_length=32)
    version = models.CharField(max_length=40)
    source = models.URLField()
    license = models.URLField()
    loinc_target = models.CharField(max_length=32, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["system", "code"], name="research_terminology_key")
        ]


class PatientReconciliation(models.Model):
    """Proposed reversible identity link, without transfer of clinical data."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="source_reconciliations"
    )
    target = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="target_reconciliations"
    )
    proposer = models.ForeignKey(User, on_delete=models.PROTECT)
    link = models.BooleanField()
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(source=models.F("target")),
                name="reconciliation_distinct_patients",
            )
        ]


class PatientReconciliationApproval(models.Model):
    proposal = models.OneToOneField(PatientReconciliation, on_delete=models.PROTECT)
    reviewer = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class LabAlertRule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    backup = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    code = models.CharField(max_length=32)
    unit = models.CharField(max_length=32)
    laboratory = models.CharField(max_length=120)
    sex = models.CharField(max_length=6, blank=True)
    min_age = models.PositiveSmallIntegerField()
    max_age = models.PositiveSmallIntegerField()
    low = models.DecimalField(max_digits=14, decimal_places=6, null=True)
    high = models.DecimalField(max_digits=14, decimal_places=6, null=True)
    sla_minutes = models.PositiveSmallIntegerField()
    evidence = models.CharField(max_length=500)
    enabled = models.BooleanField(default=True)
    version = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "organization",
                    "code",
                    "laboratory",
                    "sex",
                    "min_age",
                    "max_age",
                    "version",
                ],
                name="unique_lab_alert_rule_version",
            )
        ]


class LabAlertRuleApproval(models.Model):
    rule = models.OneToOneField(LabAlertRule, on_delete=models.PROTECT)
    reviewer = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class LabResultReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.OneToOneField(ClinicalReport, on_delete=models.PROTECT)
    outcome = models.CharField(max_length=16)
    findings = models.JSONField(default=list)
    backup = models.ForeignKey(User, on_delete=models.PROTECT, null=True, related_name="+")
    due_at = models.DateTimeField(null=True, db_index=True)
    acknowledged_at = models.DateTimeField(null=True)
    acknowledged_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, related_name="+")
    escalated_at = models.DateTimeField(null=True)
    escalation_assigned = models.BooleanField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
