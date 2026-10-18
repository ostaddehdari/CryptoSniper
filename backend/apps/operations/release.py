"""Fail-closed release-candidate evidence assembled from measured services."""

from django.conf import settings

from apps.core.deployment import deployment_status

from .hosting import hosting_capabilities
from .monitoring import service_snapshot


def release_candidate_status(*, probe_host=False):
    deployment = deployment_status(include_migrations=True)
    hosting = hosting_capabilities(
        probe_outbound=probe_host,
        probe_storage=probe_host,
    )
    operations = service_snapshot()
    environment = settings.DEPLOYMENT_ENVIRONMENT
    environment_valid = environment in {"staging", "production"}
    passed = (
        deployment["status"] == "ready"
        and hosting["status"] == "ready"
        and operations["status"] == "healthy"
        and environment_valid
        and settings.TRADING_MODE == "paper"
        and settings.LIVE_TRADING_ENABLED is False
    )
    return {
        "status": "ready" if passed else "partial",
        "release": settings.RELEASE_VERSION,
        "source_revision": settings.SOURCE_REVISION,
        "environment": environment,
        "environment_valid": environment_valid,
        "deployment": deployment,
        "hosting": hosting,
        "operations": operations,
        "trading_mode": "paper",
        "real_order_writes": False,
        "telegram": "implemented_requires_authorized_account",
        "limitations": [
            "Host/VPS evidence exists only after this command runs on the target host.",
            "All real exchange writes remain disabled by default and unverified.",
            "Telegram and AI require operator-supplied credentials and provider validation.",
        ],
    }
