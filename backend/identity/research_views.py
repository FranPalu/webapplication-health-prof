from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from identity.models import Patient, ResearchConsentEvent
from identity.security import audit
from identity.views import InputView

VERSION = 1
TEXTS = {
    "it": "Autorizzo l'uso delle mie osservazioni di laboratorio per statistiche aggregate di ricerca. Posso revocare il consenso dal portale.",
    "en": "I consent to using my laboratory observations for aggregate research statistics. I can withdraw consent from the portal.",
}


class ResearchConsentInput(serializers.Serializer):
    version = serializers.IntegerField()
    granted = serializers.BooleanField()


class ResearchConsentOutput(ResearchConsentInput):
    text = serializers.CharField()


def state(patient, user):
    event = ResearchConsentEvent.objects.filter(patient=patient).order_by("-pk").first()
    return {
        "version": VERSION,
        "text": TEXTS.get(user.locale, TEXTS["it"]),
        "granted": bool(
            event and event.actor_id == user.pk and event.version == VERSION and event.granted
        ),
    }


class ResearchConsentView(InputView):
    serializer_class = ResearchConsentInput

    @extend_schema(responses=ResearchConsentOutput)
    def get(self, request, patient_id):
        patient = get_object_or_404(Patient, pk=patient_id, account=request.user)
        return Response(state(patient, request.user))

    @extend_schema(responses=ResearchConsentOutput)
    @transaction.atomic
    def post(self, request, patient_id):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (741309621,))
        patient = get_object_or_404(
            Patient.objects.select_for_update(), pk=patient_id, account=request.user
        )
        data = self.data(request)
        if data["version"] != VERSION:
            raise ValidationError("Consent text version changed.")
        if state(patient, request.user)["granted"] != data["granted"]:
            ResearchConsentEvent.objects.create(patient=patient, actor=request.user, **data)
            audit(request.user, "research.consent_changed", patient.pk, patient.organization)
        return Response(state(patient, request.user))
