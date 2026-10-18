# چک‌لیست پذیرش نسخه پایه — Stage20

| حوزه | شاهد خودکار | شاهد اپراتور مقصد |
|---|---|---|
| Manual و Smart Paste | مسیر UI تا position close در Chromium | مرورگر عمومی مستقل |
| Spot/Margin و خروج‌ها | 10/10/80، SL، Step و Percentage روی Simulator | Binance واقعی جزو پذیرش نیست |
| Alerts/Reports/UI | notification، fee/net، timeline، timezone و viewportها | بررسی محتوای نمونه واقعی کاربر |
| Recovery/Security | fault/duplicate/race، owner boundary، secret و dependency gate | restart سرویس و restore DB جدا |
| استقرار | readiness، هفت Worker، یک Beat و package `--check` | HTTPS عمومی، offsite و rollback drill |

پذیرش CI فقط برای منبع دقیق commit و سرویس‌های disposable معتبر است. Stage19 و Stage20 تا اجرای بسته روی VPS، بررسی عمومی HTTPS، restore جدا و offsite مستقل در گزارش `partial` می‌مانند. این نسخه بدون Telegram کاملِ دامنه پایه است؛ نبود Telegram/AI نقص این release نیست و آن قابلیت‌ها نباید پیش از Stage21 ادعا شوند.
