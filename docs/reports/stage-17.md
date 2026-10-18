# استیج ۱۷ — سخت‌سازی امنیت و حفاظت داده | 0.18.0rc1

هر پنج ورک امنیتی پیاده‌سازی شده‌اند. این مرحله مجوز اجرای Live ایجاد نمی‌کند؛ `LIVE_TRADING_ENABLED` همچنان false است و 2FA تا انتخاب provider فقط readiness صادقانه دارد.

| ورک | نتیجه |
|---|---|
| S17-W01 | مالکیت object، CSRF و escaping با payload خصمانه آزموده شد؛ URL خارجی فقط HTTPS عمومی، بدون credential، localhost یا IP خصوصی پذیرفته می‌شود. |
| S17-W02 | گردش AES-GCM، ابطال و حذف ciphertext، پاک‌سازی permission response و backup قابل‌حمل AES-GCM با Scrypt؛ canary در log/API ظاهر نمی‌شود. |
| S17-W03 | password step-up با rotation شناسه نشست و اعتبار ۱۰ دقیقه برای گردش/حذف کلید؛ بدون provider هیچ کنترل 2FA فعال‌نما نیست. |
| S17-W04 | سقف body، rate limit جدا برای API/parser/subscription و fail-closed برای write هنگام خرابی limit store؛ token/session منقضی پاک و Audit append-only در بازه retention می‌ماند. |
| S17-W05 | secret/live-mode gate، dependency audit در CI و [runbook رخداد](../runbooks/security-incident.md)؛ یافته critical/high باز مانع release است. |

## شواهد فعلی

- Ruff، format، Django check، migration drift، security scan و dependency audit پاس شدند.
- [CI منبع دقیق](https://github.com/ostaddehdari/CryptoSniper/actions/runs/39108227433) روی commit `647e1cb1621b9379fb241f5c29aee399bac58ac6` با ۱۹۴ تست، PostgreSQL 16، Redis 7، Worker/Beat مستقل و Chromium کامل پاس شد؛ artifact شواهد `12129815401` است.
- لاگ ارائه‌شده اپراتور نشان می‌دهد Stage16 در ۱۸ اکتبر ۲۰۲۶ با migrationها، ده سرویس، هفت صف، readiness و HTTPS origin 200 نصب شده است. این شواهد دسترسی مرورگر عمومی مستقل نیست.

## محدودیت‌های واقعی

Provider مرحله دوم انتخاب نشده است. کلید واقعی Binance بررسی نشده و Binance write خاموش است. secret scan مکمل review و dependency audit است، نه تضمین نبود همه آسیب‌پذیری‌ها. نصب Stage18 روی VPS هنوز باید توسط اپراتور اجرا شود.
