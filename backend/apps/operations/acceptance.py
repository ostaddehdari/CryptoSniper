"""Machine-readable Stage33 hand-off contract without secret or money claims."""

from django.conf import settings

from .readiness import engine_readiness


def base_product_acceptance():
    engine = engine_readiness()
    live_switches = bool(settings.LIVE_TRADING_ENABLED and settings.LIVE_EXIT_MANAGEMENT_ENABLED)
    return {
        "stage": "S33",
        "release": settings.RELEASE_VERSION,
        "source_revision": settings.SOURCE_REVISION,
        "environment": settings.DEPLOYMENT_ENVIRONMENT,
        "status": "code_ready_operator_install_required",
        "live_writes_runtime_enabled": live_switches,
        # Backwards-compatible Stage24 fields. They describe the default safety
        # posture, while the Stage33 fields below expose the newer live gates.
        "paper_only": not live_switches,
        "real_order_writes": live_switches,
        "accepted_inputs": ["manual", "smart_paste", "telegram_feature_gated"],
        "deferred": {
            "telegram_real_account_validation": "credentials_required",
            "telegram_full_archive_validation": "authorized_channel_required",
            "channel_ai_provider_validation": "provider_credentials_required",
            "provider_specific_historical_candles": "not_implemented_binance_public_only",
            "real_binance_writes": "disabled_not_verified",
            "five_exchange_live_validation": "credentials_required",
        },
        "live_money_authorization": "separate_explicit_operator_authorization_required",
        "product": {
            "primary_ui": "react_cornix_workspace",
            "markets": ["spot_long"],
            "trade_sources": ["manual", "smart_paste", "telegram_review", "external_read"],
            "telegram_full_auto": "simulator_only",
            "historical_telegram_trading": False,
            "futures": False,
        },
        "financial_truth": {
            "real_report_source": "confirmed_exchange_receipts",
            "paper_excluded": True,
            "missing_exact_fee": "unknown_not_zero",
        },
        "security": {
            "credentials": "encrypted_at_rest_and_never_returned",
            "withdrawal_permission": "must_be_disabled",
            "sensitive_actions": "step_up_required",
            "backup": "authenticated_encryption_and_separate_restore_target",
        },
        "evidence": {
            "engine": engine,
            "server_acceptance": "docs/acceptance/stage33-server.md",
            "operator_guide": "docs/stage33-operator.fa.md",
            "release_report": "docs/reports/stage-33.md",
        },
        "external_validation": {
            "stage32_target_install": "evidence_received",
            "stage33_target_install": "pending_operator_run",
            "real_exchange_balance_comparison": "credentials_required",
            "telegram_real_account": "credentials_required",
            "ai_provider": "credentials_required",
        },
        "operator_checks_required": [
            "install the immutable Stage33 package on the target host",
            "verify public HTTPS on mobile and desktop",
            "run backup plus isolated restore verification",
            "compare permitted exchange balances and fetched-at timestamps",
        ],
    }
