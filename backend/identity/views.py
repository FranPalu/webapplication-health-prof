import secrets

import pyotp
from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from .models import (
    CareRelationship,
    Membership,
    Organization,
    Patient,
    ProfessionalVerification,
    RecoveryCode,
    User,
    UserProfile,
)
from .security import (
    PlatformAdmin,
    audit,
    cipher,
    consume_recovery,
    consume_totp,
    digest,
    rate_limit,
)
from .serializers import (
    CodeInput,
    ConfirmPasswordInput,
    EmailInput,
    LinkInput,
    LoginInput,
    MembershipInput,
    MFASetupOutput,
    OrganizationSerializer,
    PatientSerializer,
    ProfileInput,
    RecoveryOutput,
    RegisterInput,
    RelationshipInput,
    ResetInput,
    ReviewInput,
    StatusOutput,
    TokenInput,
    UserOutput,
    VerificationInput,
    VerificationOutput,
)
from .services import (
    change_membership,
    issue_token,
    org_member,
    require_org_admin,
    token_entry,
    verified_professional,
    visible_patients,
)


class InputView(GenericAPIView):
    serializer_class: type[BaseSerializer] = StatusOutput

    def data(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def status(self, value="ok", code=200):
        return Response({"status": value}, status=code)


class PublicView(InputView):
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        rate_limit(request, type(self).__name__)
        super().initial(request, *args, **kwargs)


class SessionView(PublicView):
    @extend_schema(responses=UserOutput)
    def get(self, request):
        get_token(request)
        if not request.user.is_authenticated:
            return Response({"status": "anonymous"})
        return Response(UserOutput(request.user, context={"request": request}).data)


class RegisterView(PublicView):
    serializer_class = RegisterInput

    @extend_schema(responses=StatusOutput)
    def post(self, request):
        data = self.data(request)
        with transaction.atomic():
            email = data["email"].strip().lower()
            if not User.objects.filter(email=email).exists():
                user = User.objects.create_user(**{**data, "email": email})
                issue_token(user, "verify")
                audit(user, "account.registered")
        return self.status("check_email", 202)


class VerifyView(PublicView):
    serializer_class = TokenInput

    @extend_schema(responses=StatusOutput)
    def post(self, request):
        with transaction.atomic():
            entry = token_entry(self.data(request)["token"], "verify")
            entry.user.email_verified = True
            entry.user.save(update_fields=["email_verified"])
            audit(entry.user, "email.verified")
        return self.status()


class ResendView(PublicView):
    serializer_class = EmailInput

    @extend_schema(responses=StatusOutput)
    def post(self, request):
        data = self.data(request)
        with transaction.atomic():
            user = (
                User.objects.select_for_update()
                .filter(email=data["email"].lower(), email_verified=False)
                .first()
            )
            if user:
                issue_token(user, "verify")
        return self.status("check_email", 202)


class LoginView(PublicView):
    serializer_class = LoginInput

    @extend_schema(responses=UserOutput)
    def post(self, request):
        data = self.data(request)
        user = authenticate(request, email=data["email"].strip().lower(), password=data["password"])
        if not user or not user.email_verified:
            audit(None, "login.denied")
            raise PermissionDenied("Invalid credentials or unverified email")
        login(request, user)
        request.session["auth_version"] = user.auth_version
        request.session.pop("mfa_version", None)
        audit(user, "login.password_verified")
        return Response(UserOutput(user, context={"request": request}).data)


class LogoutView(InputView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        audit(request.user, "logout")
        logout(request)
        return self.status()


class ResetRequestView(PublicView):
    serializer_class = EmailInput

    @extend_schema(responses=StatusOutput)
    def post(self, request):
        with transaction.atomic():
            user = (
                User.objects.select_for_update()
                .filter(
                    email=self.data(request)["email"].lower(), email_verified=True, is_active=True
                )
                .first()
            )
            if user:
                issue_token(user, "reset")
        return self.status("check_email", 202)


class ResetView(PublicView):
    serializer_class = ResetInput

    @extend_schema(responses=StatusOutput)
    def post(self, request):
        data = self.data(request)
        with transaction.atomic():
            entry = token_entry(data["token"], "reset")
            user = User.objects.select_for_update().get(pk=entry.user_id)
            user.set_password(data["password"])
            user.auth_version += 1
            user.save(update_fields=["password", "auth_version"])
            audit(user, "password.reset")
        return self.status()


class MFAView(InputView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        rate_limit(request, "mfa", limit=15)
        super().initial(request, *args, **kwargs)


class MFASetupView(MFAView):
    serializer_class = ConfirmPasswordInput

    @extend_schema(responses=MFASetupOutput)
    def post(self, request):
        data = self.data(request)
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if user.mfa_enabled or not user.check_password(data["password"]):
                raise PermissionDenied()
            secret = pyotp.random_base32()
            user.mfa_secret = cipher().encrypt(secret.encode()).decode()
            user.mfa_last_step = -1
            user.save(update_fields=["mfa_secret", "mfa_last_step"])
            audit(user, "mfa.enrollment_started")
        return Response(
            {"uri": pyotp.TOTP(secret).provisioning_uri(user.email, issuer_name="Health")}
        )


class MFAConfirmView(MFAView):
    serializer_class = CodeInput

    @extend_schema(responses=RecoveryOutput)
    def post(self, request):
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if user.mfa_enabled or not consume_totp(user, self.data(request)["code"]):
                raise PermissionDenied()
            user.mfa_enabled = True
            user.auth_version += 1
            user.save(update_fields=["mfa_enabled", "auth_version"])
            codes = [secrets.token_urlsafe(18) for _ in range(8)]
            RecoveryCode.objects.filter(user=user).delete()
            RecoveryCode.objects.bulk_create(
                [RecoveryCode(user=user, digest=digest(code)) for code in codes]
            )
            request.session.cycle_key()
            request.session["auth_version"] = user.auth_version
            request.session["mfa_version"] = user.auth_version
            audit(user, "mfa.enabled")
        return Response({"recovery_codes": codes})


class MFAVerifyView(MFAView):
    serializer_class = CodeInput

    @extend_schema(responses=StatusOutput)
    def post(self, request):
        user = request.user
        code = self.data(request)["code"]
        if not user.mfa_enabled or not (consume_totp(user, code) or consume_recovery(user, code)):
            audit(user, "mfa.denied")
            raise PermissionDenied()
        request.session.cycle_key()
        request.session["mfa_version"] = user.auth_version
        audit(user, "mfa.verified")
        return self.status()


class MFAResetView(InputView):
    serializer_class = ConfirmPasswordInput

    @extend_schema(responses=StatusOutput)
    def post(self, request):
        if (
            not request.user.mfa_enabled
            or request.session.get("mfa_version") != request.user.auth_version
        ):
            raise PermissionDenied()
        if not request.user.check_password(self.data(request)["password"]):
            raise PermissionDenied()
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            user.mfa_enabled = False
            user.mfa_secret = ""
            user.auth_version += 1
            user.save(update_fields=["mfa_enabled", "mfa_secret", "auth_version"])
            RecoveryCode.objects.filter(user=user).delete()
            audit(user, "mfa.reset")
        logout(request)
        return self.status()


class OrganizationsView(InputView):
    serializer_class = OrganizationSerializer

    @extend_schema(responses=OrganizationSerializer(many=True))
    def get(self, request):
        qs = Organization.objects.filter(
            membership__user=request.user, membership__active=True
        ).order_by("id")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @extend_schema(responses=OrganizationSerializer)
    def post(self, request):
        if not (
            request.user.has_profile("professional")
            or request.user.has_profile("organization_admin")
        ):
            raise PermissionDenied()
        if not request.user.has_profile("organization_admin") and not verified_professional(
            request.user
        ):
            raise PermissionDenied("Professional verification required")
        with transaction.atomic():
            organization = Organization.objects.create(**self.data(request))
            Membership.objects.create(organization=organization, user=request.user, role="admin")
            audit(request.user, "organization.created", organization.id, organization)
        return Response(self.get_serializer(organization).data, status=201)


class MembershipView(InputView):
    serializer_class = MembershipInput

    @extend_schema(responses=StatusOutput)
    def post(self, request, org_id):
        org = get_object_or_404(Organization, pk=org_id)
        require_org_admin(request.user, org)
        data = self.data(request)
        target = get_object_or_404(User, email=data["email"].lower())
        change_membership(request.user, org, target, data["role"], data["active"])
        return self.status()


class VerificationView(InputView):
    serializer_class = VerificationInput

    @extend_schema(responses=StatusOutput)
    def post(self, request):
        if not request.user.has_profile("professional"):
            raise PermissionDenied()
        with transaction.atomic():
            # A new submission invalidates the previous approval immediately.
            ProfessionalVerification.objects.update_or_create(
                user=request.user,
                defaults={
                    **self.data(request),
                    "status": "pending",
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "reason": "",
                },
            )
            audit(request.user, "professional.submitted")
        return self.status("pending", 202)


class ReviewListView(InputView):
    permission_classes = [PlatformAdmin]
    serializer_class = VerificationOutput

    @extend_schema(responses=VerificationOutput(many=True))
    def get(self, request):
        qs = ProfessionalVerification.objects.filter(status="pending").order_by("pk")
        return self.get_paginated_response(
            self.get_serializer(self.paginate_queryset(qs), many=True).data
        )


class ReviewView(InputView):
    permission_classes = [PlatformAdmin]
    serializer_class = ReviewInput

    @extend_schema(responses=StatusOutput)
    def post(self, request, user_id):
        data = self.data(request)
        with transaction.atomic():
            entry = get_object_or_404(
                ProfessionalVerification.objects.select_for_update(), user_id=user_id
            )
            if entry.user == request.user:
                raise PermissionDenied("Self approval is forbidden")
            entry.status = data["status"]
            entry.reason = data["reason"]
            entry.reviewed_by = request.user
            entry.reviewed_at = timezone.now()
            entry.save()
            audit(request.user, "professional." + entry.status, entry.user_id)
        return self.status()


class PatientsView(InputView):
    serializer_class = PatientSerializer

    @extend_schema(responses=PatientSerializer(many=True))
    def get(self, request, org_id):
        qs = visible_patients(request.user, org_id).order_by("id")
        audit(request.user, "patient.list", org_id)
        return self.get_paginated_response(
            self.get_serializer(self.paginate_queryset(qs), many=True).data
        )

    @extend_schema(responses=PatientSerializer)
    def post(self, request, org_id):
        org = get_object_or_404(Organization, pk=org_id)
        if not verified_professional(request.user) or not org_member(request.user, org):
            raise PermissionDenied()
        with transaction.atomic():
            patient = Patient.objects.create(organization=org, **self.data(request))
            CareRelationship.objects.create(patient=patient, professional=request.user)
            audit(request.user, "patient.created", patient.id, org)
        return Response(self.get_serializer(patient).data, status=201)


class PatientView(InputView):
    serializer_class = PatientSerializer

    def get(self, request, org_id, patient_id):
        patient = get_object_or_404(visible_patients(request.user, org_id), pk=patient_id)
        audit(request.user, "patient.read", patient.id, patient.organization)
        return Response(self.get_serializer(patient).data)


class RelationshipView(InputView):
    serializer_class = RelationshipInput

    @extend_schema(responses=StatusOutput)
    def post(self, request, org_id, patient_id):
        org = get_object_or_404(Organization, pk=org_id)
        require_org_admin(request.user, org)
        patient = get_object_or_404(Patient, pk=patient_id, organization=org)
        data = self.data(request)
        professional = get_object_or_404(User, pk=data["professional"])
        if not verified_professional(professional) or not org_member(professional, org):
            raise PermissionDenied()
        with transaction.atomic():
            CareRelationship.objects.update_or_create(
                patient=patient, professional=professional, defaults={"active": data["active"]}
            )
            audit(request.user, "relationship.changed", patient.id, org)
        return self.status()


class PatientLinkView(InputView):
    serializer_class = LinkInput

    @extend_schema(responses=StatusOutput)
    def post(self, request, org_id, patient_id):
        patient = get_object_or_404(visible_patients(request.user, org_id), pk=patient_id)
        if not verified_professional(request.user):
            raise PermissionDenied()
        with transaction.atomic():
            user = get_object_or_404(
                User.objects.select_for_update(),
                email=self.data(request)["email"].lower(),
                email_verified=True,
            )
            if patient.account_id:
                raise ValidationError("Patient already linked")
            issue_token(
                user, "link", {"patient_id": str(patient.id), "inviter_id": str(request.user.id)}
            )
            audit(request.user, "patient.link_invited", patient.id, patient.organization)
        return self.status("check_email", 202)


class AcceptLinkView(InputView):
    serializer_class = TokenInput

    @extend_schema(responses=StatusOutput)
    def post(self, request):
        with transaction.atomic():
            entry = token_entry(self.data(request)["token"], "link")
            if entry.user_id != request.user.pk:
                raise PermissionDenied()
            inviter = get_object_or_404(User, pk=entry.context["inviter_id"], is_active=True)
            patient = get_object_or_404(
                visible_patients(inviter).select_for_update(),
                pk=entry.context["patient_id"],
                account=None,
            )
            patient.account = request.user
            patient.save(update_fields=["account"])
            audit(request.user, "patient.link_accepted", patient.id, patient.organization)
        return self.status()


class MyPatientsView(InputView):
    serializer_class = PatientSerializer

    @extend_schema(responses=PatientSerializer(many=True))
    def get(self, request):
        qs = visible_patients(request.user).order_by("id")
        audit(request.user, "patient.list_self")
        return self.get_paginated_response(
            self.get_serializer(self.paginate_queryset(qs), many=True).data
        )


class ProfilesView(InputView):
    serializer_class = ProfileInput

    @extend_schema(responses=StatusOutput)
    def post(self, request):
        role = self.data(request)["role"]
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            UserProfile.objects.get_or_create(user=user, role=role)
            user.role = role
            user.auth_version += 1
            user.save(update_fields=["role", "auth_version"])
            audit(user, "profile.selected")
        logout(request)
        return self.status("login_required")
