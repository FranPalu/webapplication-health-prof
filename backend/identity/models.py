import uuid
from typing import ClassVar

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models
from django.db.models.functions import Lower


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
    at = models.DateTimeField(auto_now_add=True)


class RateBucket(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()


class UserProfile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=24, choices=User._meta.get_field("role").choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "role"], name="unique_user_profile")]
