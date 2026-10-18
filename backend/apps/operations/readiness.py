"""Honest engine capability matrix; implementation is not live-provider evidence."""


def engine_readiness():
    return {
        "release_mode": "paper",
        "real_order_writes": False,
        "inputs": {
            "manual": "implemented_and_simulator_tested",
            "smart_paste": "implemented_and_simulator_tested",
            "telegram": "deferred_to_s21",
        },
        "adapters": {
            "simulator_spot_long": "implemented_and_tested",
            "simulator_margin_long_short": "implemented_and_tested",
            "binance_read": "implemented_not_real_account_verified",
            "binance_sandbox_write": "disabled_not_verified",
            "binance_live_write": "disabled_not_verified",
        },
        "pipeline": {
            "risk_state_executor_exits": "shared",
            "alerts": "integrated",
            "reports": "integrated",
            "failure_recovery": "simulator_tested",
        },
        "limitations": [
            "نتیجه Simulator مدرک Sandbox یا Live نیست.",
            "کلید واقعی Binance و مجوزهای آن بررسی نشده‌اند.",
            "ارسال سفارش واقعی در build و تنظیمات غیرفعال است.",
            "Telegram و تحلیل کانال تا Stage 21 پیاده‌سازی نمی‌شوند.",
        ],
    }
