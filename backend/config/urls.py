from django.db import transaction
from django.http import JsonResponse
from django.urls import path
from drf_spectacular.views import SpectacularAPIView

from identity import analysis_views, clinical_views, fhir, payment_views, views
from identity.security import Ready


def endpoint(route, view):
    return path("api/v1/" + route, transaction.non_atomic_requests(view.as_view()))


urlpatterns = [
    path("health/", lambda request: JsonResponse({"status": "ok"})),
    path("api/v1/schema/", SpectacularAPIView.as_view(permission_classes=[Ready])),
    endpoint("auth/session/", views.SessionView),
    endpoint("auth/register/", views.RegisterView),
    endpoint("auth/profiles/", views.ProfilesView),
    endpoint("auth/verify/", views.VerifyView),
    endpoint("auth/resend/", views.ResendView),
    endpoint("auth/login/", views.LoginView),
    endpoint("auth/logout/", views.LogoutView),
    endpoint("auth/reset/request/", views.ResetRequestView),
    endpoint("auth/reset/", views.ResetView),
    endpoint("auth/mfa/setup/", views.MFASetupView),
    endpoint("auth/mfa/confirm/", views.MFAConfirmView),
    endpoint("auth/mfa/verify/", views.MFAVerifyView),
    endpoint("auth/mfa/reset/", views.MFAResetView),
    endpoint("organizations/", views.OrganizationsView),
    endpoint("organizations/<uuid:org_id>/memberships/", views.MembershipView),
    endpoint("professional/verification/", views.VerificationView),
    endpoint("admin/verifications/", views.ReviewListView),
    endpoint("admin/verifications/<uuid:user_id>/", views.ReviewView),
    endpoint("organizations/<uuid:org_id>/patients/", views.PatientsView),
    endpoint("organizations/<uuid:org_id>/patients/<uuid:patient_id>/", views.PatientView),
    endpoint(
        "organizations/<uuid:org_id>/patients/<uuid:patient_id>/relationships/",
        views.RelationshipView,
    ),
    endpoint("organizations/<uuid:org_id>/patients/<uuid:patient_id>/link/", views.PatientLinkView),
    endpoint("patients/link/accept/", views.AcceptLinkView),
    endpoint("patients/", views.MyPatientsView),
    endpoint("consents/texts/", views.ConsentTextsView),
    endpoint("consents/", views.PatientConsentView),
    endpoint("shares/", views.SharesView),
    endpoint("shares/<uuid:share_id>/revoke/", views.ShareRevokeView),
    endpoint("shares/<uuid:share_id>/patient/", views.SharedPatientView),
    endpoint("shares/<uuid:share_id>/download/", views.DownloadSharedPatientView),
    endpoint("shares/<uuid:share_id>/messages/", views.ShareMessagesView),
    endpoint("notifications/", views.NotificationsView),
    endpoint("patients/access-history/", views.AccessHistoryView),
    endpoint("break-glass/", views.BreakGlassView),
    endpoint("break-glass/patients/<uuid:patient_id>/", views.BreakGlassPatientView),
]

urlpatterns += [
    endpoint("clinical/patients/<uuid:patient_id>/folders/", clinical_views.FoldersView),
    endpoint("clinical/patients/<uuid:patient_id>/documents/", clinical_views.DocumentsView),
    endpoint("clinical/documents/<uuid:document_id>/", clinical_views.DocumentView),
    endpoint("clinical/versions/<uuid:version_id>/download/", clinical_views.DownloadView),
    endpoint("fhir/Patient/<uuid:resource_id>", clinical_views.FhirPatientView),
    endpoint("fhir/metadata", clinical_views.FhirMetadataView),
    endpoint("fhir/DocumentReference/<uuid:resource_id>", clinical_views.FhirDocumentView),
]

urlpatterns += [
    endpoint("clinical/patients/<uuid:patient_id>/reports/", fhir.ReportCreateView),
    endpoint("fhir/Organization/<uuid:resource_id>", fhir.FhirOrganizationView),
    endpoint("fhir/Practitioner/<uuid:resource_id>", fhir.FhirPractitionerView),
    endpoint("fhir/Consent/<int:resource_id>", fhir.FhirConsentView),
    endpoint("fhir/DiagnosticReport/<uuid:resource_id>", fhir.FhirReportView),
    endpoint("fhir/Observation/<uuid:resource_id>", fhir.FhirObservationView),
]

urlpatterns += [
    endpoint("clinical/versions/<uuid:version_id>/analysis/", analysis_views.JobsView),
    endpoint("clinical/analysis/<uuid:job_id>/", analysis_views.JobView),
    endpoint("clinical/analysis/<uuid:job_id>/review/", analysis_views.ReviewView),
    endpoint("clinical/opinions/<uuid:opinion_id>/publish/", analysis_views.PublishView),
    endpoint("clinical/patients/<uuid:patient_id>/opinions/", analysis_views.PublishedOpinionsView),
    endpoint("organizations/<uuid:org_id>/analysis/metrics/", analysis_views.AnalysisMetricsView),
]

urlpatterns += [
    endpoint("organizations/<uuid:org_id>/payment-prices/", payment_views.PriceView),
    endpoint("payments/checkout/", payment_views.CheckoutView),
    endpoint("payments/orders/", payment_views.OrdersView),
    endpoint("payments/orders/<uuid:order_id>/refund/", payment_views.RefundView),
]
