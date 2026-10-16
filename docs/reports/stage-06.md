# Stage 06 — سیگنال و Inbox | v0.6.0rc1

تاریخ ۱۶ اکتبر ۲۰۲۶. وضعیت **partial** با وجود آزمون موفق CI و نصب موفق VPS بر اساس لاگ کاربر؛ وابستگی‌ها و پذیرش مرورگر عمومی هنوز باز هستند.

| ورک | پیاده‌سازی |
|---|---|
| S06-W01 | SignalSource با تنها سه روش canonical: Manual، Smart Paste و Telegram (فقط placeholder برای Stage21). SourceTransport interface بدون اتصال خارجی. |
| S06-W02 | RawSignal با اصل متن و payload و SHA256، external_id scoped و revisionهای append-only برای حفظ متن نخستین و نسخه‌های بعدی؛ duplicate هم‌منبع دوباره سیگنال ایجاد نمی‌کند |
| S06-W03 | Signal، SignalTarget (۱ تا ۳ هدف)، confidence فنی، parser_version و immutable revision records، ارتباط مالکیت با کاربر و حساب/بازار |
| S06-W04 | وضعیت‌های New/Parsed/Needs Review/Approved/Rejected/Executed/Failed؛ transitionهای restricted با row lock، optimistic revision و audit، Executed/Failed رزرو شده برای engine |
| S06-W05 | Inbox فارسی RTL، مقایسه Raw/Structured، فیلتر status/source/date، اصلاح، Reject/Approve، API خصوصی و تاریخچه |

**امنیت:** ورود متن به معامله واقعی منجر نمی‌شود. Parser قالبی Stage07 و Telethon/AI Stage21 هستند. Approved Snapshot را تنظیمات بعدی تغییر نمی‌دهند. Confidence فنی «احتمال سود» نیست.

**محدودیت:** تست Provider واقعی Binance مرحله S03 و بندهای پذیرش قبلی هنوز کامل نشده‌اند. آزمون‌های CI و VPS باید مستند شوند و تا آن زمان Stage06 `partial` است.

## نتیجه آزمایش و انتشار
- [CI موفق Stage06](https://github.com/ostaddehdari/CryptoSniper/actions/runs/38939379593): commit آزمایش‌شده `2718263fb39c37e615a667ead65b039c9f659a58`؛ **۶۶ تست Pytest موفق**، بدون failure یا skip ثبت‌شده.
- Ruff، Django system check، `makemigrations --check --dry-run`، مهاجرت‌های واقعی PostgreSQL و Redis/Workers/Beat موفق شدند.
- Chromium smoke: ورود، ساخت سیگنال در `/inbox/receive/`، مرور متن، ثبت ساختار، تأیید انسانی، صفحات موبایل ۳۲۰/۳۹۰/۷۶۸ بدون overflow و خطای JS. شواهد artifact شناسه `12062622061`.
- [GitHub Release stage06-v0.6.0rc1-deploy](https://github.com/ostaddehdari/CryptoSniper/releases/tag/stage06-v0.6.0rc1-deploy) شامل ZIP تجمعی و نصب‌کننده Ubuntu است که `bash --check` و SHA256 تأیید شدند.
- ZIP SHA-256: `c3febb83e3224ca3aa9137983294432a2f71902b29b4b633434e1c56239900c3`.
- Installer SHA-256: `5902ec443430aa1cf8a8e8d1a1adb9a5e90bf424a1c554fbb8615335890d73e9`.

## وضعیت پذیرش
**پنج ورک اجرا و CI پاس شده‌اند، اما Stage06 به‌علت پیش‌نیازهای formal هنوز `partial` است**: S03 بررسی credential واقعی Binance، S04/S05 بندهای باقی‌مانده پذیرش و پذیرش دستی رابط از مرورگر عمومی هنوز بسته نشده‌اند. اتصال تلگرام و تحلیل AI در Stage21 باقی است. موتور معامله واقعی هنوز غیرفعال است.

## تأیید نصب روی VPS طبق لاگ ارسالی کاربر — ۱۶ اکتبر ۲۰۲۶

این شواهد از خروجی ترمینال **ارسالی کاربر** روی Ubuntu 24.04 استخراج شده‌اند؛ آزمون مستقلی از اینترنت عمومی یا ورود مرورگری کاربر انجام نشده است.

- اجرای دستور رسمی `scripts/deploy.sh` نسخه `stage06-v0.6.0rc1-deploy` را با کنترل SHA-256 هر دو فایل تأیید کرده است.
- `CHECK_OK` و سپس نصب با حفظ تنظیمات خصوصی و keyring رمزگذاری‌شده انجام شد.
- migration `signals.0001_initial` روی PostgreSQL با `OK` اعمال و فایل‌های static جمع‌آوری شدند.
- readiness داخلی: PostgreSQL، Redis Cache/Broker/Results همگی `true`.
- پردازش‌های Orders و Reports و ضربان Beat موفق؛ سرویس‌های Redis، Web، Orders، Reports و Beat فعال گزارش شدند.
- `nginx -t` موفق؛ مسیرهای readiness و login از مبدأ HTTPS محلی هر دو HTTP 200 دادند.
- خروجی نهایی: `INSTALL_OK: CryptoSniper Stage06 v0.6.0rc1` و `DEPLOY_OK`.
- اخطار `duplicate MIME type "text/html"` در `/etc/nginx/snippets/statichost-sitelinkmacker.conf:43` باقی است، اما مانع صحت‌سنجی Nginx یا نصب این مرحله نشده و نباید بدون بررسی بر سایر سایت‌های سرور اعمال تغییر کرد.

**نتیجه:** استقرار Stage06 روی VPS طبق گزارش ارسالی موفق است. آزمون دستی فرم Inbox در مرورگر عمومی و تست API واقعی Binance هنوز تأیید نشده‌اند؛ هیچ سفارش واقعی فعال نشده است. وضعیت رسمی `partial` حفظ می‌شود.
