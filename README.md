# CryptoSniper

سامانه پایتونی دریافت، اجرای و مدیریت سیگنال رمزارز با Django، PostgreSQL، Redis و Celery، رابط Mobile-First و حالت روشن پیش‌فرض.

**برنامه: ۲۲ استیج × ۵ ورک = ۱۱۰ ورک.** کد آزمایشی **0.22.0rc1** جریان کامل وریفای حساب Telegram، آرشیو قابل‌ادامه از نخستین پیام، قالب‌های چندگانه و سنجش تاریخی محافظه‌کارانه را همراه adapterهای Spot برای Nobitex، LBank، WEEX، Ourbit و Bitunix دارد. credential واقعی هیچ provider آزمون نشده و `LIVE_TRADING_ENABLED=false` است. Full-Auto Telegram فقط Paper/Simulator می‌ماند؛ Futures/Perpetual و Margin واقعی غیرفعال‌اند.

- [گزارش تحویل و شواهد استیج ۱](docs/reports/stage-01.md)
- [گزارش تحویل و شواهد استیج ۲](docs/reports/stage-02.md)
- [گزارش پیاده‌سازی و محدودیت استیج ۳](docs/reports/stage-03.md)
- [Dashboard و شواهد استیج ۱۳](docs/reports/stage-13.md)
- [مدیریت معاملات و شواهد استیج ۱۴](docs/reports/stage-14.md)
- [محاسبات و گزارش‌های استیج ۱۵](docs/reports/stage-15.md)
- [تجربهٔ موبایل، دسکتاپ و PWA استیج ۱۶](docs/reports/stage-16.md)
- [سخت‌سازی امنیت و حفاظت داده استیج ۱۷](docs/reports/stage-17.md)
- [شبیه‌ساز کامل و اعتبارسنجی Paper استیج ۱۸](docs/reports/stage-18.md)
- [استقرار و عملیات استیج ۱۹](docs/reports/stage-19.md)
- [پذیرش نسخه پایه استیج ۲۰](docs/reports/stage-20.md)
- [Telethon، تحلیل کانال و پنج صرافی Spot در استیج ۲۱](docs/reports/stage-21.md)
- [تکمیل Telegram و ارزیابی تاریخی در استیج ۲۲](docs/reports/stage-22.md)
- [راهنمای کاربر](docs/user-guide.md) و [راهنمای ادمین](docs/admin-guide.md)
- [راهنمای نصب و اجرا](docs/setup.md)
- [بررسی خودکار در GitHub Actions](https://github.com/ostaddehdari/CryptoSniper/actions)

- [برنامه کامل استیج‌ها و ورک‌ها](docs/roadmap.md)
- [پروتکل اجرای یک‌باره هر استیج و ثبت کامیت](docs/execution-protocol.md)
- [قواعد معماری و معامله](docs/architecture.md)
- [نگاشت تمام بخش‌های پروپوزال](docs/requirements-traceability.md)
- [برنامه ماشینی](docs/plan.json) و [وضعیت اجرا](docs/progress.json)
- [متن اصلی پروپوزال](docs/source/proposal-original.txt)

نسخه نخست: Paper Spot/Margin و Live Spot محدود؛ Futures و Perpetual برای آینده. Manual Entry، Smart Paste و اتصال/آرشیو Telegram حاضرند. Live فقط با کلید Read+Spot بدون برداشت، IP allowlist و فعال‌سازی صریح ادمین مجاز است.

برای ادامه:

> Release 0.21 را پس از سبزشدن CI با `--check` بررسی و سپس روی VPS نصب کن؛ بعد credentialها را فقط در UI رمزنگاری‌شده وارد و اتصال خواندنی را پیش از Live تأیید کن.

پس از اتمام، همین دستور با شماره استیج بعد اجرا می‌شود. درخواست یک استیج مجوز رفتن خودکار به استیج بعد نیست. ثبت کد در GitHub به‌معنی مجوز اجرای معامله با پول واقعی یا استقرار روی سرور تعیین‌نشده نیست.

اجرای کامل نیازمند هاست پایتونی با Worker دائمی، PostgreSQL، Redis، scheduler و HTTPS است. Production نیازی به runtime Node.js ندارد.


## استقرار و به‌روزرسانی از GitHub با یک دستور

فایل `scripts/deploy.sh` ZIP و نصب‌کنندهٔ [Release رسمی 0.21](https://github.com/ostaddehdari/CryptoSniper/releases/tag/stage21-v0.21.0rc1-deploy) را دانلود می‌کند، SHA-256 هر دو را با مقادیر ثابت بررسی می‌کند، سپس صحت بسته را با `--check` می‌سنجد و نصب/ارتقا را انجام می‌دهد. رمزهای خصوصی، دیتابیس، keyring و ورود موجود در ارتقای مدیریت‌شده محفوظ می‌مانند. Release از commit ثابت `e315e1983bb916ed8867a721b583e9b2c55eb93a` ساخته شده و SHA-256 فایل ZIP برابر `8a44ba2e8e1d61806a122d93bf92f6e3eccc85fa291fc3f51c327469141e0d41` است.

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
