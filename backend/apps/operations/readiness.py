"""Stage23 capability matrix based on implemented code, not provider-account evidence."""

from django.conf import settings


def engine_readiness():
    return {
        "release_mode": "live_accounts_real_spot_entry_feature_gated",
        "real_order_writes": bool(settings.LIVE_TRADING_ENABLED),
        "inputs": {
            "manual": "implemented",
            "smart_paste": "implemented",
            "telegram": "implemented_review_and_archive_flow",
        },
        "adapters": {
            "bitunix_spot": "implemented_requires_operator_credentials_validation",
            "lbank_spot": "implemented_requires_operator_credentials_validation",
            "nobitex_spot": "implemented_requires_operator_credentials_validation",
            "weex_spot": "implemented_requires_operator_credentials_validation",
            "ourbit_spot": "implemented_requires_operator_credentials_validation",
            "binance_new_connections": "hidden_from_stage23_ui",
            "simulator": "retired_from_ui_and_automation",
        },
        "pipeline": {
            "fix_loss_position_sizing": "implemented_advisory",
            "explicit_live_spot_entry": "implemented_fail_closed_feature_gated",
            "external_exchange_read_observation": "implemented_where_adapter_read_endpoints_support_it",
            "managed_live_tp_sl_trailing": "not_enabled",
            "live_margin_execution": "not_implemented_plan_only",
            "alerts": "integrated",
            "reports": "integrated",
            "failure_recovery": "implemented_for_live_order_outbox_and_observation",
        },
        "telegram": {
            "telethon": "implemented",
            "verification_flow": "implemented",
            "full_archive": "implemented_from_first_accessible_message",
            "message_search": "implemented",
            "template_parser": "implemented",
            "legacy_full_auto": "disabled",
            "live_auto_order_from_channel": "not_enabled_review_required",
        },
        "wallets": {
            "exchange_api_accounts": "implemented_read_trade_without_withdrawal",
            "browser_wallet_public_address": "implemented_non_custodial_reference",
            "watch_only_address": "implemented",
            "seed_phrase_or_private_key_storage": "prohibited",
            "walletconnect_full_session": "requires_operator_project_configuration",
        },
        "limitations": [
            "LIVE_TRADING_ENABLED controls whether real exchange order writes are allowed.",
            "Managed automatic live TP/SL/trailing exits are not enabled in Stage23.",
            "Margin plans may be displayed but live borrow/repay execution is not implemented.",
            "External orders/fills are visible only where the selected exchange adapter exposes reliable read endpoints.",
            "Wallet connections are non-custodial references/browser ownership flows; CryptoSniper never needs a seed phrase or private key.",
        ],
    }
