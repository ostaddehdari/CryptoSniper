from django.apps import AppConfig


class OperationsConfig(AppConfig):
    name = "apps.operations"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import signals  # noqa: F401
