from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from identity.models import Membership
from identity.security import audit
from identity.views import InputView


class Coordinates(serializers.Serializer):
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=-180, max_value=180
    )


class NearbyInput(Coordinates):
    radius_km = serializers.IntegerField(min_value=1, max_value=50, default=10)


class LocationView(InputView):
    serializer_class = Coordinates

    @extend_schema(responses=Coordinates)
    @transaction.atomic
    def post(self, request, org_id):
        if request.session.get("mfa_version") != request.user.auth_version:
            raise PermissionDenied()
        member = get_object_or_404(
            Membership, user=request.user, active=True, role="admin", organization_id=org_id
        )
        data = self.data(request)
        org = member.organization
        org.latitude, org.longitude = data["latitude"], data["longitude"]
        org.save(update_fields=["latitude", "longitude"])
        audit(request.user, "directory.location_updated", org.pk, org)
        return Response(Coordinates(org).data)


class NearbyView(InputView):
    serializer_class = NearbyInput

    @extend_schema(parameters=[NearbyInput], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        with connection.cursor() as cursor:
            cursor.execute(
                """
                WITH origin AS (SELECT ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography AS point),
                places AS (
                    SELECT id, name, kind,
                        ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography AS point
                    FROM identity_organization
                    WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                    AND kind IN ('clinic', 'hospital', 'practice', 'pharmacy')
                )
                SELECT id, name, kind, ST_Distance(places.point, origin.point)
                FROM places CROSS JOIN origin
                WHERE ST_DWithin(places.point, origin.point, %s)
                ORDER BY 4, id LIMIT 50
            """,
                [values["longitude"], values["latitude"], values["radius_km"] * 1000],
            )
            return Response(
                [
                    {"id": identifier, "name": name, "kind": kind, "distance_m": round(distance)}
                    for identifier, name, kind, distance in cursor.fetchall()
                ]
            )
