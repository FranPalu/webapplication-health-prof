from django.db import transaction
from django.urls import path
from drf_spectacular.views import SpectacularAPIView

from config.health import liveness, readiness
from identity import (
    analysis_registry,
    analysis_views,
    appointment_views,
    clinical_safety,
    clinical_views,
    directory_views,
    fhir,
    fhir_gateway,
    interop_bulk,
    interop_hl7,
    interop_oauth,
    interop_pacs,
    lab_orders,
    medication_safety,
    patient_identification,
    payment_views,
    pharmacy_views,
    reconciliation,
    research_release_views,
    research_views,
    views,
)
from identity.security import Ready


def endpoint(route, view, **options):
    return path("api/v1/" + route, transaction.non_atomic_requests(view.as_view(**options)))


urlpatterns = [
    path("health/", liveness),
    path("health/ready/", readiness),
    path("api/v1/schema/", SpectacularAPIView.as_view(permission_classes=[Ready])),
    endpoint("auth/session/", views.SessionView),
    endpoint("auth/register/", views.RegisterView),
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
    endpoint(
        "fhir/Patient/<uuid:resource_id>", fhir_gateway.FhirGatewayView, resource_type="Patient"
    ),
    endpoint("fhir/metadata", fhir_gateway.FhirCapabilityView),
    endpoint(
        "fhir/DocumentReference/<uuid:resource_id>",
        fhir_gateway.FhirGatewayView,
        resource_type="DocumentReference",
    ),
]

urlpatterns += [
    endpoint(
        "clinical/patients/<uuid:patient_id>/identifiers/",
        patient_identification.PatientIdentifierView,
    ),
    endpoint(
        "clinical/patients/<uuid:patient_id>/reconciliations/",
        reconciliation.PatientReconciliationView,
    ),
    endpoint(
        "clinical/reconciliations/<uuid:reconciliation_id>/approve/",
        reconciliation.PatientReconciliationApprovalView,
    ),
    endpoint("clinical/patients/<uuid:patient_id>/encounters/", fhir.EncounterCreateView),
    endpoint("organizations/<uuid:org_id>/lab-rules/", clinical_safety.LabRuleView),
    endpoint(
        "organizations/<uuid:org_id>/lab-rules/<uuid:rule_id>/approve/",
        clinical_safety.LabRuleApprovalView,
    ),
    endpoint("clinical/patients/<uuid:patient_id>/result-reviews/", clinical_safety.LabReviewView),
    endpoint(
        "clinical/result-reviews/<uuid:review_id>/acknowledge/",
        clinical_safety.LabReviewAcknowledgmentView,
    ),
    endpoint("clinical/patients/<uuid:patient_id>/lab-orders/", lab_orders.LabOrderView),
    endpoint("clinical/result-reviews/<uuid:review_id>/complete/", lab_orders.LabCompletionView),
    endpoint(
        "clinical/patients/<uuid:patient_id>/medication-checks/",
        medication_safety.MedicationSafetyView,
    ),
    endpoint(
        "clinical/medication-checks/<uuid:check_id>/override/",
        medication_safety.MedicationOverrideView,
    ),
    endpoint("clinical/patients/<uuid:patient_id>/reports/", fhir.ReportCreateView),
    endpoint("clinical/reports/<uuid:report_id>/corrections/", fhir.ReportCorrectionView),
    endpoint(
        "fhir/Encounter/<uuid:resource_id>", fhir_gateway.FhirGatewayView, resource_type="Encounter"
    ),
    endpoint(
        "fhir/Organization/<uuid:resource_id>",
        fhir_gateway.FhirGatewayView,
        resource_type="Organization",
    ),
    endpoint(
        "fhir/Practitioner/<uuid:resource_id>",
        fhir_gateway.FhirGatewayView,
        resource_type="Practitioner",
    ),
    endpoint(
        "fhir/Consent/<int:resource_id>", fhir_gateway.FhirGatewayView, resource_type="Consent"
    ),
    endpoint(
        "fhir/DiagnosticReport/<uuid:resource_id>",
        fhir_gateway.FhirReportInstanceView,
        resource_type="DiagnosticReport",
    ),
    endpoint(
        "fhir/DiagnosticReport/<uuid:resource_id>/_history/<int:version>",
        fhir_gateway.FhirGatewayView,
        resource_type="DiagnosticReport",
    ),
    endpoint(
        "fhir/Provenance/<uuid:resource_id>-v<int:version>",
        fhir_gateway.FhirGatewayView,
        resource_type="Provenance",
    ),
    endpoint(
        "fhir/ServiceRequest/<uuid:resource_id>",
        fhir_gateway.FhirGatewayView,
        resource_type="ServiceRequest",
    ),
    endpoint(
        "fhir/Observation/<uuid:resource_id>",
        fhir_gateway.FhirGatewayView,
        resource_type="Observation",
    ),
]

urlpatterns += [
    endpoint("clinical/versions/<uuid:version_id>/analysis/", analysis_views.JobsView),
    endpoint("clinical/analysis/<uuid:job_id>/", analysis_views.JobView),
    endpoint(
        "organizations/<uuid:org_id>/analysis/registry/", analysis_registry.AnalysisPolicyView
    ),
    endpoint("clinical/analysis/<uuid:job_id>/review-start/", analysis_views.StartReviewView),
    endpoint("clinical/analysis/<uuid:job_id>/incidents/", analysis_views.AnalysisIncidentView),
    endpoint("clinical/analysis/<uuid:job_id>/review/", analysis_views.ReviewView),
    endpoint("clinical/opinions/<uuid:opinion_id>/sign/", analysis_views.SignOpinionView),
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

urlpatterns += [
    endpoint("organizations/<uuid:org_id>/appointment-slots/", appointment_views.SlotsView),
    endpoint("appointments/slots/<uuid:slot_id>/book/", appointment_views.BookSlotView),
    endpoint("appointments/bookings/", appointment_views.MyBookingsView),
    endpoint(
        "appointments/bookings/<uuid:booking_id>/cancel/", appointment_views.CancelBookingView
    ),
]

urlpatterns += [
    endpoint("organizations/<uuid:org_id>/pharmacy/catalog/", pharmacy_views.CatalogView),
    endpoint(
        "organizations/<uuid:org_id>/pharmacy/reservations/", pharmacy_views.PharmacyQueueView
    ),
    endpoint("pharmacy/items/<uuid:item_id>/reserve/", pharmacy_views.ReserveView),
    endpoint("pharmacy/reservations/", pharmacy_views.ReservationListView),
    endpoint(
        "pharmacy/reservations/<uuid:reservation_id>/decision/", pharmacy_views.PharmacyDecisionView
    ),
]

urlpatterns += [
    endpoint(
        "appointments/bookings/<uuid:booking_id>/reschedule/", appointment_views.MoveBookingView
    ),
    endpoint("organizations/<uuid:org_id>/location/", directory_views.LocationView),
    endpoint("directory/nearby/", directory_views.NearbyView),
]


urlpatterns += [
    endpoint("patients/<uuid:patient_id>/research-consent/", research_views.ResearchConsentView),
]

urlpatterns += [
    endpoint("research/catalog/", research_release_views.ResearchCatalogView),
    endpoint(
        "organizations/<uuid:org_id>/research/requests/", research_release_views.ResearchAccessView
    ),
    endpoint("research/admin/requests/", research_release_views.ResearchReviewListView),
    endpoint(
        "research/admin/requests/<uuid:request_id>/decision/",
        research_release_views.ResearchReviewView,
    ),
    endpoint(
        "research/requests/<uuid:request_id>/export/", research_release_views.ResearchExportView
    ),
]

urlpatterns += [
    endpoint("fhir/.well-known/smart-configuration", interop_oauth.SmartDiscoveryView),
    endpoint(
        "organizations/<uuid:org_id>/interop/applications/", interop_oauth.InteropApplicationsView
    ),
    endpoint(
        "organizations/<uuid:org_id>/interop/applications/<uuid:application_id>/revoke/",
        interop_oauth.ApplicationRevocationView,
    ),
    endpoint("clinical/patients/<uuid:patient_id>/interop/grants/", interop_oauth.InteropGrantView),
    endpoint("interop/grants/<uuid:grant_id>/revoke/", interop_oauth.GrantRevocationView),
] + [
    endpoint(
        "fhir/" + resource,
        (
            fhir_gateway.FhirReportCollectionView
            if resource == "DiagnosticReport"
            else fhir_gateway.FhirGatewayView
        ),
        resource_type=resource,
    )
    for resource in fhir_gateway.READERS
]

urlpatterns += [endpoint("interop/patients/<uuid:patient_id>/hl7/", interop_hl7.HL7ReceiptView)]

urlpatterns += [
    endpoint("fhir/$export", interop_bulk.ResearchBulkStartView),
    endpoint("interop/research-exports/<uuid:job_id>/", interop_bulk.ResearchBulkStatusView),
    endpoint(
        "interop/research-exports/<uuid:job_id>/MeasureReport.ndjson",
        interop_bulk.ResearchBulkFileView,
    ),
]

urlpatterns += [
    endpoint("interop/patients/<uuid:patient_id>/pacs/", interop_pacs.PacsImportView),
    endpoint("dicom-web/studies", interop_pacs.DicomWebView),
    endpoint("dicom-web/studies/<str:study_uid>/<path:suffix>", interop_pacs.DicomWebView),
]

urlpatterns += [
    endpoint("interop/hl7-receipts/<uuid:receipt_id>/", interop_hl7.HL7ReceiptDetailView)
]

urlpatterns += [endpoint("fhir/Binary/<uuid:resource_id>", fhir_gateway.FhirBinaryView)]
