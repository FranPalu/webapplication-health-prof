from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema


class SessionScheme(OpenApiAuthenticationExtension):
    target_class = "identity.security.StrictSessionAuthentication"
    name = "sessionAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": "sessionid",
            "description": "Server session. Mutating requests also require X-CSRFToken from csrftoken cookie.",
        }


class SmartPatientScheme(OpenApiAuthenticationExtension):
    target_class = "identity.interop_oauth.SmartBearerAuthentication"
    name = "smartPatientBearer"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "description": "Delegated RFC 7662 opaque token; patient, tenant, approved application and current grant bound. No local OAuth server.",
        }


class SmartResearchScheme(OpenApiAuthenticationExtension):
    target_class = "identity.interop_oauth.SmartResearchAuthentication"
    name = "smartResearchBearer"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "description": "Delegated user/MeasureReport.rs token with fresh MFA, approved research request, tenant membership and application.",
        }


class InteropPathSchema(AutoSchema):
    """Distinct operation IDs for type-level searches and instance reads."""

    def get_operation_id(self):
        import re

        return re.sub(r"[^A-Za-z0-9_]", "_", self.path.strip("/")) + "_" + self.method.lower()
