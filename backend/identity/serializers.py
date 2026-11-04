from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from .models import ConsentTextVersion, Organization, Patient, ProfessionalVerification, Share, User


class PasswordField(serializers.CharField):
    def __init__(self, **kwargs):
        super().__init__(
            write_only=True, trim_whitespace=False, min_length=12, max_length=128, **kwargs
        )

    def run_validation(self, data=serializers.empty):
        value = super().run_validation(data)
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value


class RegisterInput(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = PasswordField()
    role = serializers.ChoiceField(
        choices=["patient", "professional", "researcher", "organization_admin"]
    )
    locale = serializers.ChoiceField(choices=["it", "en"], default="it")


class LoginInput(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)


class TokenInput(serializers.Serializer):
    token = serializers.CharField(max_length=100, write_only=True)


class EmailInput(serializers.Serializer):
    email = serializers.EmailField()


class ResetInput(TokenInput):
    password = PasswordField()


class CodeInput(serializers.Serializer):
    code = serializers.CharField(max_length=100, write_only=True)


class ConfirmPasswordInput(serializers.Serializer):
    password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)


class UserOutput(serializers.ModelSerializer):
    requires_mfa = serializers.BooleanField()
    profiles = serializers.SerializerMethodField()

    def get_profiles(self, obj) -> list[str]:
        return sorted(set([obj.role, *obj.userprofile_set.values_list("role", flat=True)]))

    mfa_verified = serializers.SerializerMethodField()
    verification_status = serializers.SerializerMethodField()
    is_platform_admin = serializers.BooleanField(source="is_staff")

    def get_mfa_verified(self, obj) -> bool:
        return (
            obj.mfa_enabled
            and self.context["request"].session.get("mfa_version") == obj.auth_version
        )

    def get_verification_status(self, obj) -> str:
        entry = ProfessionalVerification.objects.filter(user=obj).first()
        return entry.status if entry else "not_submitted"

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "role",
            "locale",
            "email_verified",
            "requires_mfa",
            "mfa_enabled",
            "mfa_verified",
            "verification_status",
            "is_platform_admin",
            "profiles",
        ]


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "kind"]
        read_only_fields = ["id"]


class MembershipInput(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=["admin", "professional", "researcher"])
    active = serializers.BooleanField(default=True)


class VerificationInput(serializers.Serializer):
    register = serializers.CharField(max_length=200)
    license_number = serializers.CharField(max_length=100)


class ReviewInput(serializers.Serializer):
    status = serializers.ChoiceField(choices=["approved", "rejected"])
    reason = serializers.CharField(max_length=500)


class VerificationOutput(serializers.ModelSerializer):
    class Meta:
        model = ProfessionalVerification
        fields = ["user", "register", "license_number", "status", "reason", "reviewed_at"]


class PatientSerializer(serializers.ModelSerializer):
    def validate_birth_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Invalid birth date")
        return value

    class Meta:
        model = Patient
        fields = ["id", "organization", "first_name", "last_name", "birth_date", "email"]
        read_only_fields = ["id", "organization"]


class RelationshipInput(serializers.Serializer):
    professional = serializers.UUIDField()
    active = serializers.BooleanField(default=True)


class LinkInput(serializers.Serializer):
    email = serializers.EmailField()


class StatusOutput(serializers.Serializer):
    status = serializers.CharField()


class MFASetupOutput(serializers.Serializer):
    uri = serializers.CharField()


class RecoveryOutput(serializers.Serializer):
    recovery_codes = serializers.ListField(child=serializers.CharField())


class ProfileInput(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=["patient", "professional", "researcher", "organization_admin"]
    )


class ShareInput(serializers.Serializer):
    patient = serializers.UUIDField()
    recipient_user = serializers.UUIDField(required=False)
    recipient_organization = serializers.UUIDField(required=False)
    scope = serializers.ChoiceField(choices=["item", "chart"])
    permissions = serializers.ListField(
        child=serializers.ChoiceField(choices=["view", "download", "comment", "reshare"]),
        allow_empty=False,
        max_length=4,
    )
    purpose = serializers.CharField(max_length=300, trim_whitespace=True)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    parent_share = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if bool(attrs.get("recipient_user")) == bool(attrs.get("recipient_organization")):
            raise serializers.ValidationError("Specify exactly one recipient")
        if len(set(attrs["permissions"])) != len(attrs["permissions"]):
            raise serializers.ValidationError("Duplicate permissions")
        if attrs.get("expires_at") and attrs["expires_at"] <= timezone.now():
            raise serializers.ValidationError("Expiration must be in the future")
        return attrs


class ConsentInput(serializers.Serializer):
    share = serializers.UUIDField()
    text_version = serializers.IntegerField()
    locale = serializers.ChoiceField(choices=["it", "en"])
    decision = serializers.ChoiceField(choices=["granted", "revoked"])


class SecureMessageInput(serializers.Serializer):
    body = serializers.CharField(max_length=5000, trim_whitespace=True)


class BreakGlassInput(serializers.Serializer):
    patient = serializers.UUIDField()
    reason = serializers.CharField(max_length=1000, trim_whitespace=True)


class ShareOutput(serializers.ModelSerializer):
    active = serializers.SerializerMethodField()
    consent_decision = serializers.SerializerMethodField()

    def get_active(self, obj) -> bool:
        from .services import share_is_active

        return share_is_active(obj)

    def get_consent_decision(self, obj) -> str:
        from .models import PatientConsent

        decision = (
            PatientConsent.objects.filter(share=obj)
            .order_by("-created_at", "-pk")
            .values_list("decision", flat=True)
            .first()
        )
        return decision or "pending"

    class Meta:
        model = Share
        fields = [
            "id",
            "patient",
            "granted_by",
            "recipient_user",
            "recipient_organization",
            "scope",
            "permissions",
            "purpose",
            "expires_at",
            "revoked_at",
            "created_at",
            "active",
            "consent_decision",
        ]
        read_only_fields = fields


class ConsentTextOutput(serializers.ModelSerializer):
    class Meta:
        model = ConsentTextVersion
        fields = ["purpose", "version", "locale", "text", "content_hash", "published_at"]


class ConsentEventOutput(serializers.Serializer):
    share = serializers.UUIDField()
    purpose = serializers.CharField()
    version = serializers.IntegerField()
    locale = serializers.CharField()
    content_hash = serializers.CharField()
    decision = serializers.ChoiceField(choices=["granted", "revoked"])
    created_at = serializers.DateTimeField()


class SecureMessageOutput(serializers.Serializer):
    id = serializers.IntegerField()
    sender = serializers.UUIDField()
    body = serializers.CharField()
    created_at = serializers.DateTimeField()


class SecureMessageCreatedOutput(serializers.Serializer):
    id = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class NotificationOutput(serializers.Serializer):
    id = serializers.IntegerField()
    category = serializers.CharField()
    resource_id = serializers.UUIDField(allow_null=True)
    created_at = serializers.DateTimeField()
    read = serializers.BooleanField()


class AccessHistoryOutput(serializers.Serializer):
    actor = serializers.UUIDField(allow_null=True)
    action = serializers.CharField()
    at = serializers.DateTimeField()


class BreakGlassOutput(serializers.Serializer):
    id = serializers.IntegerField()
    expires_at = serializers.DateTimeField()
