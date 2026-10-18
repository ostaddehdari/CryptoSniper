"""Machine-readable Stage21 product delivery contract."""

from django.conf import settings

from .readiness import engine_readiness


def base_product_acceptance():
    engine = engine_readiness()
    return {
        "release": settings.RELEASE_VERSION,
        "source_revision": settings.SOURCE_REVISION,
        "environment": settings.DEPLOYMENT_ENVIRONMENT,
        "status": "base_product_ready_for_operator_acceptance",
        "paper_only": not settings.LIVE_TRADING_ENABLED,
        "real_order_writes": bool(settings.LIVE_TRADING_ENABLED),
        "accepted_inputs": ["manual", "smart_paste", "telegram_feature_gated"],
        "accepted_markets": ["spot_long", "margin_long", "margin_short"],
        "accepted_pipeline": [
            "preview",
            "risk",
            "paper_execution",
            "tp_sl_trailing",
            "alerts",
            "reports",
            "recovery",
        ],
        "evidence": {
            "engine": engine,
            "user_guide": "docs/user-guide.md",
            "admin_guide": "docs/admin-guide.md",
            "checklist": "docs/acceptance/stage20-checklist.md",
        },
        "deferred": {
            "telegram_real_account_validation": "credentials_required",
            "channel_ai_provider_validation": "provider_credentials_required",
            "real_binance_writes": "disabled_not_verified",
            "five_exchange_live_validation": "credentials_required",
        },
        "operator_checks_required": [
            "install immutable package on the target host",
            "verify public HTTPS with an independent browser",
            "run encrypted restore drill against a separate database",
            "configure and verify an independent offsite backup destination",
        ],
    }
