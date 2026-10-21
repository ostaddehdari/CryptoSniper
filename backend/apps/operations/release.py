"""Fail-closed Stage23 release evidence assembled from measured services."""

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
    mode_valid = settings.TRADING_MODE == "live"
    passed = (
        deployment["status"] == "ready"
        and hosting["status"] == "ready"
        and operations["status"] == "healthy"
        and environment_valid
        and mode_valid
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
        "trading_mode": settings.TRADING_MODE,
        "paper_ui": False,
        "real_order_writes": bool(settings.LIVE_TRADING_ENABLED),
        "telegram": "implemented_review_first",
        "limitations": [
            "Real order writes remain feature-gated by LIVE_TRADING_ENABLED and per-account permissions.",
            "Managed automatic live TP/SL/trailing is not enabled until provider exit cycles are verified.",
            "Margin borrow/repay execution is not implemented.",
            "WalletConnect full sessions require operator project configuration; seed/private keys are never accepted.",
        ],
    }
