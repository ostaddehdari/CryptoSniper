"""Machine-readable Stage23 product delivery contract."""

from django.conf import settings

from .readiness import engine_readiness


def base_product_acceptance():
    engine = engine_readiness()
    return {
        "release": settings.RELEASE_VERSION,
        "source_revision": settings.SOURCE_REVISION,
        "environment": settings.DEPLOYMENT_ENVIRONMENT,
        "status": "stage23_live_account_ui_ready_for_operator_acceptance",
        "paper_only": False,
        "real_order_writes": bool(settings.LIVE_TRADING_ENABLED),
        "accepted_inputs": ["manual", "smart_paste", "telegram_review"],
        "accepted_markets": ["spot_long", "margin_plan_only"],
        "accepted_pipeline": [
            "preview",
            "risk_and_fix_loss",
            "explicit_live_spot_entry",
            "alerts",
            "reports",
            "external_exchange_observation",
            "recovery",
        ],
        "evidence": {
            "engine": engine,
            "wallet_guide": "docs/WALLET_CONNECTION_GUIDE_FA.md",
            "stage23_notes": "docs/STAGE23_REACT_LIVE_UI.md",
        },
        "deferred": {
            "managed_live_tp_sl_trailing": "not_enabled_until_provider_exit_cycle_is_implemented_and_verified",
            "live_margin_borrow_repay": "not_implemented",
            "walletconnect_session": "requires_operator_walletconnect_project_id_and_provider_package",
            "hardware_wallet_transaction_signing": "not_enabled_public_address_or_browser_wallet_only",
            "provider_live_validation": "requires_operator_credentials_per_exchange",
        },
        "operator_checks_required": [
            "verify every exchange API key has withdrawal disabled",
            "verify IP allow-list where the provider supports it",
            "run connection diagnostics for each live account",
            "verify a small explicitly-confirmed live order before normal use",
            "configure backups and test rollback before enabling live writes",
        ],
    }
