"""Fixed aggregate projection. There is no row-level research export."""

from django.db.models import Count, F, OuterRef, Subquery
from django.db.models.functions import ExtractYear

from identity.models import ClinicalObservation, ResearchConsentEvent
from identity.research_views import VERSION

MIN_PATIENTS = 10


def eligible_cells():
    latest = ResearchConsentEvent.objects.filter(
        patient_id=OuterRef("report__patient_id")
    ).order_by("-pk")
    return (
        ClinicalObservation.objects.annotate(
            consent=Subquery(latest.values("granted")[:1]),
            consent_version=Subquery(latest.values("version")[:1]),
            consent_actor=Subquery(latest.values("actor_id")[:1]),
            year=ExtractYear("report__effective_at"),
        )
        .filter(
            consent=True,
            consent_version=VERSION,
            consent_actor=F("report__patient__account_id"),
            code__regex=r"^[0-9]{1,12}-[0-9]$",
        )
        .values("year", "code")
        .annotate(patients=Count("report__patient__account_id", distinct=True))
        .filter(patients__gte=MIN_PATIENTS)
        .order_by("year", "code")
    )
