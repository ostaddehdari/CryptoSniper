"""Honest Stage22 capability matrix; code is not provider/account evidence."""

from django.conf import settings


def engine_readiness():
    return {
        "release_mode": "paper_default_live_spot_feature_gated",
        "real_order_writes": bool(settings.LIVE_TRADING_ENABLED),
        "inputs": {
            "manual": "implemented_and_simulator_tested",
            "smart_paste": "implemented_and_simulator_tested",
            "telegram": "implemented_not_real_account_verified",
        },
        "adapters": {
            "simulator_spot_long": "implemented_and_tested",
            "simulator_margin_long_short": "implemented_and_tested",
            "binance_read": "implemented_not_real_account_verified",
            "binance_sandbox_write": "disabled_not_verified",
            "binance_live_write": "disabled_not_verified",
            "nobitex_spot": "implemented_not_real_account_verified",
            "lbank_spot": "implemented_not_real_account_verified",
            "weex_spot": "implemented_not_real_account_verified",
            "ourbit_spot": "implemented_not_real_account_verified",
            "bitunix_spot": "implemented_not_real_account_verified",
        },
        "pipeline": {
            "risk_state_executor_exits": "shared",
            "alerts": "integrated",
            "reports": "integrated",
            "failure_recovery": "simulator_tested",
            "direct_spot_outbox": "implemented_fail_closed_not_real_account_verified",
        },
        "telegram": {
            "telethon": "implemented_not_real_account_verified",
            "verification_flow": "implemented_not_real_code_verified",
            "full_archive": "implemented_not_real_channel_verified",
            "template_parser": "versioned_multi_template_unit_tested",
            "historical_outcomes": "binance_public_ohlc_conservative",
            "ai": "implemented_provider_not_configured",
            "full_auto": "simulator_paper_only",
        },
        "limitations": [
            "نتیجه Simulator مدرک Sandbox یا Live نیست.",
            "کلید واقعی هیچ‌یک از پنج صرافی جدید بررسی نشده است.",
            "ارسال سفارش واقعی به‌صورت پیش‌فرض در تنظیمات غیرفعال است.",
            "Telegram/AI بدون API ID، session و provider واقعی تأییدشده محسوب نمی‌شوند.",
            "کندل تاریخی providerهای پنج صرافی پیاده نشده و ارزیابی فعلی Binance عمومی است.",
        ],
    }
