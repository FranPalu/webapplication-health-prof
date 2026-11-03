from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from .models import Organization, Patient, ProfessionalVerification, User


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
