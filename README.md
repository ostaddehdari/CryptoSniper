# CryptoSniper

سامانه پایتونی دریافت، اجرای و مدیریت سیگنال رمزارز با Django، PostgreSQL، Redis و Celery، رابط Mobile-First و حالت روشن پیش‌فرض.

**برنامه: ۲۱ استیج × ۵ ورک = ۱۰۵ ورک.** نسخهٔ تجمعی آزمایشی **0.16.0rc1** شامل کد استیج‌های ۱ تا ۱۶ است: گزارش Decimal gross/net P/L و fee/interest، aggregateهای timezone، CSV/SVG و drill-down، همراه تجربهٔ نهایی موبایل/دسکتاپ و PWA امن. ۱۵۶ آزمون و PostgreSQL/Redis/هفت Worker/Beat/Chromium در CI منبع دقیق پاس شده‌اند؛ شواهد و محدودیت‌ها در گزارش‌های استیج ۱۵ و ۱۶ ثبت شده‌اند. نصب موفق Stage14 با لاگ کاربر تأیید شده است؛ نصب نسخه 0.16 و پذیرش عمومی مرورگر هنوز باز است. اجرای واقعی سفارش، Margin/Short و مدیریت معاملات External غیرفعال‌اند؛ تأیید Binance واقعی همچنان باز است.

- [گزارش تحویل و شواهد استیج ۱](docs/reports/stage-01.md)
- [گزارش تحویل و شواهد استیج ۲](docs/reports/stage-02.md)
- [گزارش پیاده‌سازی و محدودیت استیج ۳](docs/reports/stage-03.md)
- [Dashboard و شواهد استیج ۱۳](docs/reports/stage-13.md)
- [مدیریت معاملات و شواهد استیج ۱۴](docs/reports/stage-14.md)
- [محاسبات و گزارش‌های استیج ۱۵](docs/reports/stage-15.md)
- [تجربهٔ موبایل، دسکتاپ و PWA استیج ۱۶](docs/reports/stage-16.md)
- [راهنمای نصب و اجرا](docs/setup.md)
- [بررسی خودکار در GitHub Actions](https://github.com/ostaddehdari/CryptoSniper/actions)

- [برنامه کامل استیج‌ها و ورک‌ها](docs/roadmap.md)
- [پروتکل اجرای یک‌باره هر استیج و ثبت کامیت](docs/execution-protocol.md)
- [قواعد معماری و معامله](docs/architecture.md)
- [نگاشت تمام بخش‌های پروپوزال](docs/requirements-traceability.md)
- [برنامه ماشینی](docs/plan.json) و [وضعیت اجرا](docs/progress.json)
- [متن اصلی پروپوزال](docs/source/proposal-original.txt)

نسخه نخست: Spot و Margin؛ Futures و Perpetual برای آینده. Manual Entry و Smart Paste در نسخه پایه آماده می‌شوند. **اتصال Telethon، خواندن کانال‌ها و تحلیل قالبی یا هوش مصنوعی فقط آخرین استیج، S21، هستند.**

برای ادامه:

> نسخهٔ تجمعی 0.16 را نصب و Reports، خروجی‌ها، رابط موبایل و رفتار offline را بررسی کن. مرحله بعد S17 است و فقط با درخواست جدید اجرا می‌شود؛ تأیید امن حساب Binance همچنان باز است.

پس از اتمام، همین دستور با شماره استیج بعد اجرا می‌شود. درخواست یک استیج مجوز رفتن خودکار به استیج بعد نیست. ثبت کد در GitHub به‌معنی مجوز اجرای معامله با پول واقعی یا استقرار روی سرور تعیین‌نشده نیست.

اجرای کامل نیازمند هاست پایتونی با Worker دائمی، PostgreSQL، Redis، scheduler و HTTPS است. Production نیازی به runtime Node.js ندارد.


## استقرار و به‌روزرسانی از GitHub با یک دستور

از این به بعد تمام نسخه‌ها ابتدا در GitHub ثبت می‌شوند. فایل `scripts/deploy.sh` ZIP و نصب‌کنندهٔ pin‌شده به یک commit تغییرناپذیر را دانلود می‌کند، SHA-256 هر دو را با مقادیر ثابت بررسی می‌کند، سپس صحت بسته را سنجیده و نصب/ارتقا را انجام می‌دهد. رمزهای خصوصی و دیتابیس موجود در ارتقای مدیریت‌شده محفوظ می‌مانند. ساخت صفحهٔ GitHub Release این نسخه با محدودیت دسترسی GitHub Actions (`403`) روبه‌رو شد؛ همان bytes تأییدشدهٔ artifact در `release-assets/` مخزن نگهداری و با commit ثابت دریافت می‌شوند.

دستور سرور Ubuntu (دسترسی sudo/root لازم است):

```bash
curl -fsSL --retry 3 -o /tmp/cryptosniper-deploy.sh https://raw.githubusercontent.com/ostaddehdari/CryptoSniper/main/scripts/deploy.sh && sudo bash /tmp/cryptosniper-deploy.sh
```

برای دانلود و بررسی **بدون نصب**، به انتهای دستور `--check` اضافه کنید.

برای تشخیص فقط‌خواندنی مشکل HTTPS/Nginx (بدون تغییر یا restart سرویس‌ها):

```bash
curl -fsSL --retry 3 -o /tmp/cryptosniper-diagnose-nginx.sh https://raw.githubusercontent.com/ostaddehdari/CryptoSniper/main/scripts/diagnose-nginx.sh && sudo bash /tmp/cryptosniper-diagnose-nginx.sh
```

در صورت شکست اتصال HTTPS در نصب‌کننده، تغییرات مسیر Nginx بازگردانده می‌شوند. هنگام خطای ۴۰۴، به‌جای تلاش کورکورانه برای تغییر vhostهای سایر سرویس‌ها، ابتدا خروجی ابزار تشخیص بررسی شود. سرویس‌ها و migrationهای Stage 03 ممکن است موفق بوده باشند، حتی اگر مسیریابی عمومی وب هنوز آماده نباشد.

**امنیت:** این دستور کد مخزن رسمی خودتان را روی سرور با دسترسی root اجرا می‌کند؛ پیش از اجرای هر نسخه جدید، تغییرات مخزن را بازبینی کنید. هیچ API Key یا رمز مدیریتی را در issue، commit یا گزارش عمومی منتشر نکنید.

- [گزارش اجرایی استیج ۴](docs/reports/stage-04.md) — توسعه مستقل آغاز شده؛ تأیید CI/Provider و نصب نهایی در انتظار شواهد است.

- [استیج ۵ — برنامه‌های دستی و پیش‌نمایش](docs/reports/stage-05.md): نسخه آزمایشی `0.5.0rc1`، Draft/Ready، بدون اجرای سفارش.

- [Stage06 Signal Inbox](docs/reports/stage-06.md): نسخه آزمایشی v0.6.0rc1، ثبت خام و بازبینی تاریخچه‌دار، بدون Telegram/AI و سفارش واقعی.

- [Stage07 Smart Paste](docs/reports/stage-07.md) و [Stage08 Paper Execution](docs/reports/stage-08.md): نسخه تجمعی آزمایشی 0.8.0rc1، فقط Paper/Simulator و بدون سفارش واقعی Binance.

- [Stage09 TP/SL](docs/reports/stage-09.md) و [Stage10 Trailing](docs/reports/stage-10.md): خروج حفاظتی فقط Paper، نسخه آزمایشی 0.10.0rc1.

- [Stage11 Operations & Recovery](docs/reports/stage-11.md) و [Stage12 Alerts & Notifications](docs/reports/stage-12.md): نسخه تجمعی آزمایشی 0.12.0rc1، فقط Paper/مشاهده فقط‌خواندنی؛ اجرای واقعی Binance غیرفعال.
