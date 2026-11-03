from drf_spectacular.extensions import OpenApiAuthenticationExtension


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
