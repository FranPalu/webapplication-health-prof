"""Fixed aggregate projection. There is no row-level research export."""

import hmac

from django.conf import settings
from django.db.models import BinaryField, CharField, Count, F, Func, OuterRef, Subquery, Value
from django.db.models.functions import Cast, ExtractYear

from identity.models import ClinicalObservation, ResearchConsentEvent, ResearchTerminology
from identity.research_views import VERSION

MIN_PATIENTS = 10


def eligible_cells(minimum=MIN_PATIENTS):
    key = hmac.digest(
        settings.SECRET_KEY.encode(), b"claria-research-projection-v1", "sha256"
    ).hex()
    latest = ResearchConsentEvent.objects.filter(
        patient_id=OuterRef("report__patient_id")
    ).order_by("-pk")
    return (
        ClinicalObservation.objects.annotate(
            consent=Subquery(latest.values("granted")[:1]),
            consent_version=Subquery(latest.values("version")[:1]),
            consent_actor=Subquery(latest.values("actor_id")[:1]),
            year=ExtractYear("report__effective_at"),
            research_account=Func(
                Cast("report__patient__account_id", CharField()),
                Value(key),
                Value("sha256"),
                function="HMAC",
                output_field=BinaryField(),
            ),
        )
        .filter(
            consent=True,
            consent_version=VERSION,
            consent_actor=F("report__patient__account_id"),
            code__regex=r"^[0-9]{1,12}-[0-9]$",
            code__in=ResearchTerminology.objects.filter(system="loinc", active=True).values("code"),
        )
        .values("year", "code")
        .annotate(patients=Count("research_account", distinct=True))
        .filter(patients__gte=minimum)
        .order_by("year", "code")
    )
