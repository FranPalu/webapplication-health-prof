import secrets
from datetime import timedelta

import pyotp
from django.contrib.auth import authenticate, login, logout
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
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
    AuditEvent,
    BreakGlassAccess,
    CareRelationship,
    ConsentTextVersion,
    InAppNotification,
    Membership,
    Organization,
    Patient,
    PatientConsent,
    ProfessionalVerification,
    RecoveryCode,
    SecureMessage,
    Share,
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
    AccessHistoryOutput,
    BreakGlassInput,
    BreakGlassOutput,
    CodeInput,
    ConfirmPasswordInput,
    ConsentEventOutput,
    ConsentInput,
    ConsentTextOutput,
    EmailInput,
    LinkInput,
    LoginInput,
    MembershipInput,
    MFASetupOutput,
    NotificationOutput,
    OrganizationSerializer,
    PatientSerializer,
    ProfileInput,
    RecoveryOutput,
    RegisterInput,
    RelationshipInput,
    ResetInput,
    ReviewInput,
    SecureMessageCreatedOutput,
    SecureMessageInput,
    SecureMessageOutput,
    ShareInput,
    ShareOutput,
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
    share_is_active,
    share_recipient_queryset,
    token_entry,
    user_is_share_participant,
    verified_professional,
    visible_patients,
)


def notify_user_id(user_id, category, resource_id):
    InAppNotification.objects.create(user_id=user_id, category=category, resource_id=resource_id)
    user = User.objects.filter(pk=user_id).only("email", "locale").first()
    if user:
        subject = (
            "Health — secure notification" if user.locale == "en" else "Health — notifica protetta"
        )
        body = (
            "You have a new notification in the Health portal. Sign in to view it securely."
            if user.locale == "en"
            else "Hai una nuova notifica nel portale Health. Accedi per visualizzarla in modo sicuro."
        )
        transaction.on_commit(
            lambda: send_mail(subject, body, None, [user.email], fail_silently=True), robust=True
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


class SessionView(InputView):
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        # Only the session read uses the authenticated account as its quota key.
        super().initial(request, *args, **kwargs)
        rate_limit(request, type(self).__name__, by_user=True)

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


class ConsentTextsView(InputView):
    serializer_class = ConsentTextOutput
    pagination_class = None

    def get(self, request):
        qs = ConsentTextVersion.objects.order_by("purpose", "locale", "-version")
        latest: dict[tuple[str, str], ConsentTextVersion] = {}
        for entry in qs:
            latest.setdefault((entry.purpose, entry.locale), entry)
        return Response(self.get_serializer(list(latest.values()), many=True).data)


class SharesView(InputView):
    serializer_class = ShareInput

    @extend_schema(responses=ShareOutput(many=True))
    def get(self, request):
        received = share_recipient_queryset(request.user).filter(
            Exists(PatientConsent.objects.filter(share_id=OuterRef("pk"), decision="granted"))
        )
        qs = Share.objects.filter(
            Q(granted_by=request.user)
            | Q(patient__account=request.user)
            | Q(pk__in=received.values("pk"))
        ).select_related("patient", "granted_by", "recipient_user", "recipient_organization")
        return self.get_paginated_response(
            ShareOutput(
                self.paginate_queryset(qs.order_by("-created_at")),
                many=True,
                context=self.get_serializer_context(),
            ).data
        )

    @transaction.atomic
    @extend_schema(request=ShareInput, responses=ShareOutput)
    def post(self, request):
        data = self.data(request)
        parent = None
        if data.get("parent_share"):
            parent = get_object_or_404(Share.objects.select_for_update(), pk=data["parent_share"])
            if not share_is_active(parent) or not user_is_share_participant(request.user, parent):
                raise PermissionDenied()
            if "reshare" not in parent.permissions:
                raise PermissionDenied("Re-sharing is not permitted")
            patient = parent.patient
            if str(patient.pk) != str(data["patient"]):
                raise PermissionDenied("A re-share must refer to the parent resource")
        else:
            patient = get_object_or_404(visible_patients(request.user), pk=data["patient"])
        from identity.clinical import descendant_folders, visible_documents
        from identity.models import ClinicalFolder

        document = None
        folder = None
        if data.get("document"):
            document = get_object_or_404(
                visible_documents(request.user).exclude(kind__in=["psychology", "prescription"]),
                pk=data["document"],
                patient=patient,
            )
        if data.get("folder"):
            folder = get_object_or_404(ClinicalFolder, pk=data["folder"], patient=patient)
        if (
            parent
            and parent.scope == "item"
            and parent.document_id != getattr(document, "pk", None)
        ):
            raise PermissionDenied("A re-share cannot change its resource")
        if parent and parent.scope == "folder":
            allowed_folders = descendant_folders([parent.folder_id])
            selected_folder = document.folder_id if document else getattr(folder, "pk", None)
            if selected_folder not in allowed_folders:
                raise PermissionDenied("A re-share cannot expand its folder scope")
        if not patient.account_id:
            raise ValidationError("Patient account must be linked before requesting consent")
        recipient_user = None
        recipient_org = None
        if data.get("recipient_user"):
            recipient_user = get_object_or_404(User, pk=data["recipient_user"], is_active=True)
            if recipient_user == request.user or not (
                verified_professional(recipient_user) or recipient_user == patient.account
            ):
                raise PermissionDenied(
                    "Recipient must be the linked patient or a verified professional"
                )
        else:
            recipient_org = get_object_or_404(Organization, pk=data["recipient_organization"])
        if parent:
            if data["purpose"] != parent.purpose:
                raise PermissionDenied("A re-share must preserve its purpose")
            if parent.scope == "item" and data["scope"] != "item":
                raise PermissionDenied("A re-share cannot expand its scope")
            if not set(data["permissions"]).issubset(parent.permissions):
                raise PermissionDenied("A re-share cannot increase permissions")
            if parent.expires_at and (
                not data.get("expires_at") or data["expires_at"] > parent.expires_at
            ):
                raise PermissionDenied("A re-share cannot outlive its parent")
        share = Share.objects.create(
            patient=patient,
            document=document,
            folder=folder,
            granted_by=request.user,
            recipient_user=recipient_user,
            recipient_organization=recipient_org,
            scope=data["scope"],
            permissions=data["permissions"],
            purpose=data["purpose"],
            expires_at=data.get("expires_at"),
            parent=parent,
        )
        notify_user_id(patient.account_id, "share.pending_consent", share.id)
        audit(request.user, "share.created", share.id, patient.organization)
        return Response(ShareOutput(share, context=self.get_serializer_context()).data, status=201)


class ShareRevokeView(InputView):
    @transaction.atomic
    def post(self, request, share_id):
        share = get_object_or_404(
            Share.objects.select_for_update().filter(
                Q(granted_by=request.user) | Q(patient__account=request.user)
            ),
            pk=share_id,
        )
        if share.revoked_at is None:
            share.revoked_at = timezone.now()
            share.save(update_fields=["revoked_at"])
            # Revocation cascades to all descendants, so no copied grant survives.
            frontier = [share.pk]
            while frontier:
                children = list(Share.objects.filter(parent_id__in=frontier, revoked_at=None))
                child_ids = [child.pk for child in children]
                for child in children:
                    child.revoked_at = timezone.now()
                    child.save(update_fields=["revoked_at"])
                    audit(
                        request.user, "share.revoked_cascade", child.id, child.patient.organization
                    )
                frontier = child_ids
            audit(request.user, "share.revoked", share.id, share.patient.organization)
        return self.status("revoked")


class PatientConsentView(InputView):
    serializer_class = ConsentInput
    pagination_class = None

    @extend_schema(responses=ConsentEventOutput(many=True))
    def get(self, request):
        events = (
            PatientConsent.objects.filter(patient__account=request.user)
            .select_related("text_version", "share")
            .order_by("-created_at")[:100]
        )
        return Response(
            [
                {
                    "share": str(event.share_id),
                    "purpose": event.text_version.purpose,
                    "version": event.text_version.version,
                    "locale": event.text_version.locale,
                    "content_hash": event.text_version.content_hash,
                    "decision": event.decision,
                    "created_at": event.created_at,
                }
                for event in events
            ]
        )

    @transaction.atomic
    @extend_schema(request=ConsentInput, responses=StatusOutput)
    def post(self, request):
        data = self.data(request)
        share = get_object_or_404(
            Share.objects.select_for_update().filter(patient__account=request.user),
            pk=data["share"],
        )
        text = get_object_or_404(
            ConsentTextVersion,
            purpose="care_sharing",
            version=data["text_version"],
            locale=data["locale"],
        )
        latest_version = (
            ConsentTextVersion.objects.filter(purpose=text.purpose, locale=text.locale)
            .order_by("-version")
            .values_list("version", flat=True)
            .first()
        )
        if text.version != latest_version:
            raise ValidationError("Only the current consent text version can be accepted")
        if data["decision"] == "granted" and (
            share.revoked_at is not None
            or (share.expires_at and share.expires_at <= timezone.now())
        ):
            raise ValidationError("A revoked or expired share cannot be activated")
        event = PatientConsent.objects.create(
            patient=share.patient,
            share=share,
            text_version=text,
            actor=request.user,
            decision=data["decision"],
        )
        audit(request.user, f"consent.{event.decision}", share.id, share.patient.organization)
        if event.decision == "granted":
            if share.recipient_user_id:
                notify_user_id(share.recipient_user_id, "share.active", share.id)
            elif share.recipient_organization_id:
                for member_id in Membership.objects.filter(
                    organization=share.recipient_organization,
                    active=True,
                    role__in=["professional", "admin"],
                ).values_list("user_id", flat=True):
                    notify_user_id(member_id, "share.active", share.id)
        else:
            if share.recipient_user_id:
                notify_user_id(share.recipient_user_id, "share.revoked", share.id)
            elif share.recipient_organization_id:
                for member_id in Membership.objects.filter(
                    organization=share.recipient_organization,
                    active=True,
                    role__in=["professional", "admin"],
                ).values_list("user_id", flat=True):
                    notify_user_id(member_id, "share.revoked", share.id)
        return self.status(event.decision)


class SharedPatientView(InputView):
    serializer_class = PatientSerializer

    @extend_schema(responses=PatientSerializer)
    def get(self, request, share_id):
        share = get_object_or_404(
            share_recipient_queryset(request.user),
            pk=share_id,
            document__isnull=True,
            folder__isnull=True,
        )
        if not share_is_active(share) or "view" not in share.permissions:
            audit(request.user, "share.access_denied", share.id, share.patient.organization)
            raise PermissionDenied()
        audit(request.user, "share.patient_read", share.id, share.patient.organization)
        return Response(self.get_serializer(share.patient).data)


class DownloadSharedPatientView(InputView):
    serializer_class = PatientSerializer

    @extend_schema(responses=PatientSerializer)
    def get(self, request, share_id):
        share = get_object_or_404(
            share_recipient_queryset(request.user),
            pk=share_id,
            document__isnull=True,
            folder__isnull=True,
        )
        if not share_is_active(share) or "download" not in share.permissions:
            audit(request.user, "share.download_denied", share.id, share.patient.organization)
            raise PermissionDenied()
        audit(request.user, "share.patient_downloaded", share.id, share.patient.organization)
        response = Response(PatientSerializer(share.patient).data)
        response["Content-Disposition"] = 'attachment; filename="patient-record.json"'
        return response


class ShareMessagesView(InputView):
    serializer_class = SecureMessageInput
    pagination_class = None

    def get_share(self, request, share_id):
        participants = Q(granted_by=request.user) | Q(patient__account=request.user)
        recipients = share_recipient_queryset(request.user).values("pk")
        share = get_object_or_404(
            Share.objects.filter(participants | Q(pk__in=recipients)), pk=share_id
        )
        if not share_is_active(share):
            raise PermissionDenied()
        return share

    @extend_schema(responses=SecureMessageOutput(many=True))
    def get(self, request, share_id):
        share = self.get_share(request, share_id)
        if "comment" not in share.permissions:
            raise PermissionDenied()
        messages = SecureMessage.objects.filter(share=share).order_by("-created_at", "-pk")[:100]
        audit(request.user, "share.messages_read", share.id, share.patient.organization)
        return Response(
            [
                {
                    "id": message.id,
                    "sender": str(message.sender_id),
                    "body": message.body,
                    "created_at": message.created_at,
                }
                for message in reversed(messages)
            ]
        )

    @extend_schema(request=SecureMessageInput, responses=SecureMessageCreatedOutput)
    @transaction.atomic
    def post(self, request, share_id):
        share = self.get_share(request, share_id)
        if "comment" not in share.permissions:
            raise PermissionDenied()
        message = SecureMessage.objects.create(
            share=share, sender=request.user, body=self.data(request)["body"]
        )
        recipient_ids = set()
        if share.recipient_user_id:
            recipient_ids.add(share.recipient_user_id)
        else:
            recipient_ids.update(
                Membership.objects.filter(
                    organization=share.recipient_organization,
                    active=True,
                    role__in=["professional", "admin"],
                ).values_list("user_id", flat=True)
            )
        recipient_ids.add(share.granted_by_id)
        if share.patient.account_id:
            recipient_ids.add(share.patient.account_id)
        recipient_ids.discard(request.user.pk)
        for user_id in recipient_ids:
            notify_user_id(user_id, "share.message", share.id)
        audit(request.user, "share.message_sent", share.id, share.patient.organization)
        return Response({"id": message.id, "created_at": message.created_at}, status=201)


class NotificationsView(InputView):
    pagination_class = None

    @extend_schema(responses=NotificationOutput(many=True))
    def get(self, request):
        items = InAppNotification.objects.filter(user=request.user).order_by("-created_at")[:100]
        return Response(
            [
                {
                    "id": item.id,
                    "category": item.category,
                    "resource_id": item.resource_id,
                    "created_at": item.created_at,
                    "read": item.read_at is not None,
                }
                for item in items
            ]
        )


class AccessHistoryView(InputView):
    pagination_class = None

    @extend_schema(responses=AccessHistoryOutput(many=True))
    def get(self, request):
        patient_ids = list(
            Patient.objects.filter(account=request.user).values_list("id", flat=True)
        )
        if not patient_ids:
            return Response([])
        share_ids = Share.objects.filter(patient_id__in=patient_ids).values_list("id", flat=True)
        resource_ids = [str(value) for value in patient_ids] + [str(value) for value in share_ids]
        from django.db.models.functions import Cast

        from identity.models import ClinicalDocumentVersion, ClinicalObservation, ClinicalReport

        versions = ClinicalDocumentVersion.objects.filter(
            document__patient_id__in=patient_ids
        ).exclude(document__kind="psychology")
        reports = ClinicalReport.objects.filter(patient_id__in=patient_ids)
        observations = ClinicalObservation.objects.filter(report__in=reports)
        from django.db.models import CharField

        clinical_ids = Q()
        for records in (versions, reports, observations):
            clinical_ids |= Q(
                resource_id__in=records.annotate(
                    text_id=Cast("pk", output_field=CharField())
                ).values("text_id")
            )
        events = AuditEvent.objects.filter(Q(resource_id__in=resource_ids) | clinical_ids)
        return Response(
            [
                {
                    "actor": str(event.actor_id) if event.actor_id else None,
                    "action": event.action,
                    "at": event.at,
                }
                for event in events.order_by("-at")[:200]
            ]
        )


class BreakGlassView(InputView):
    serializer_class = BreakGlassInput

    @transaction.atomic
    @extend_schema(request=BreakGlassInput, responses=BreakGlassOutput)
    def post(self, request):
        data = self.data(request)
        if not verified_professional(request.user) or len(data["reason"].strip()) < 15:
            raise PermissionDenied("Verified professional and a specific emergency reason required")
        organizations = Membership.objects.filter(
            user=request.user,
            active=True,
            role__in=["professional", "admin"],
            organization__break_glass_enabled=True,
        ).values("organization_id")
        patient = get_object_or_404(
            Patient.objects.filter(organization_id__in=organizations), pk=data["patient"]
        )
        now = timezone.now()
        entry = BreakGlassAccess.objects.create(
            patient=patient,
            professional=request.user,
            reason=data["reason"].strip(),
            expires_at=now + timedelta(minutes=15),
        )
        if patient.account_id:
            InAppNotification.objects.create(
                user_id=patient.account_id, category="security.break_glass", resource_id=None
            )
        audit(request.user, "break_glass.started", patient.id, patient.organization)
        return Response({"id": entry.id, "expires_at": entry.expires_at}, status=201)


class BreakGlassPatientView(InputView):
    serializer_class = PatientSerializer

    @extend_schema(responses=PatientSerializer)
    def get(self, request, patient_id):
        entry = (
            BreakGlassAccess.objects.filter(
                patient_id=patient_id, professional=request.user, expires_at__gt=timezone.now()
            )
            .order_by("-created_at")
            .first()
        )
        if not entry or not verified_professional(request.user):
            raise PermissionDenied()
        membership = org_member(request.user, entry.patient.organization)
        if (
            not membership
            or membership.role not in ("professional", "admin")
            or not membership.organization.break_glass_enabled
        ):
            raise PermissionDenied()
        audit(
            request.user, "break_glass.patient_read", entry.patient_id, entry.patient.organization
        )
        return Response(PatientSerializer(entry.patient).data)
