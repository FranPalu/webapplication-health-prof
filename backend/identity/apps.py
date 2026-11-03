from django.apps import AppConfig


class IdentityConfig(AppConfig):
    name = "identity"

    def ready(self):
        from . import schema  # noqa: F401
