# Stage 08 — موتور Paper و مدیریت Position v0.8.0rc1

پیاده‌سازی هر پنج ورک S08-W01..05: Trade/Order/Fill/Position، رویداد افزایشی و وضعیت‌های جداگانه، request_key UUID، client_order_id یکتا، outbox پایدار، Worker/Celery Beat و مسیر دستی یا SmartPaste→TradePlan→Paper. Snapshot تأییدشده مستقل از تنظیمات جدید کاربر باقی می‌ماند.

**کنترل ریسک:** فقط Spot Long روی Simulator داخلی Paper. درخواست Binance Live، Margin بدون borrow/repay تأییدشده و Futures/Perpetual رد می‌شوند. رزرو سرمایه در PostgreSQL با lock حساب و سقف تعداد/سرمایه؛ شناسه Fill یکتا از دوباره‌شماری جلوگیری می‌کند. بعد از timeout/crash حین ارسال، وضعیت UNCERTAIN ثبت می‌شود و هرگز بدون reconciliation دوباره ارسال نمی‌شود. تأیید مرورگر شرط اجرای Worker نیست.

**محدودیت:** Simulator نسخه نخست Market order را تماماً پر می‌کند؛ partial fill در لایه record_fill و تست پوشش داده شده است. سفارش TP/SL و Trailing هنوز وارد موتور نشده‌اند (S09/S10)؛ در این نسخه، اجرای Paper **بدون سفارش خروج محافظتی** است. برای حساب واقعی هرگز فعال نیست.

**وضعیت:** partial تا CI و تأیید نصب VPS، معیارهای رسمی قبلی و Binance واقعی.

## شواهد نهایی آزمایش و انتشار ۱۶ اکتبر ۲۰۲۶

- [GitHub CI #38954065804](https://github.com/ostaddehdari/CryptoSniper/actions/runs/38954065804) موفق؛ **۷۶ آزمون Pytest موفق** روی PostgreSQL واقعی، Redis، Celery Worker/Beat و Smoke مرورگر Chromium (دسکتاپ/موبایل).
- کد تست‌شده Release: `04d84c0e5ef75155bce32a173c2441e20f0f5080`؛ [انتشار تجمعی Stage07+08](https://github.com/ostaddehdari/CryptoSniper/releases/tag/stage08-v0.8.0rc1-deploy).
- ZIP SHA256: `24a5ff7a700b2c56cca80af10681617bb1a8f22b9533757bc6fe8c2e2ad14fbd`، نصب‌کننده SHA256: `43604c51082bc1341b608d069a3185761126d54e0b13a1f458b7ae07a20671cd`.
- آزمون کامل Smart Paste→Inbox→Trade Plan→Paper→Worker→Position اجرا شده و مرورگر پس از ثبت سفارش آزمایشی می‌تواند بسته شود؛ وابستگی به جلسه مرورگر وجود ندارد.
- استقرار روی VPS کاربر هنوز انجام نشده و آزمون واقعی Binance S03-W04 باز است. وضعیت رسمی تا پذیرش همه پیش‌نیازها **partial** باقی می‌ماند.

**محدودیت مهم:** Position آزمایشی Stage08 فاقد سفارش خروج محافظتی TP/SL و Trailing اجرایی است. این قابلیت‌ها در S09 و S10 تکمیل می‌شوند. هیچ سفارش واقعی به Binance ارسال نمی‌شود.

## نتیجه نصب سرور طبق لاگ کاربر — ۱۶ اکتبر ۲۰۲۶

- نسخه `v0.8.0rc1` از انتشار رسمی GitHub و با کنترل SHA-256 دو فایل نصب شده؛ `CHECK_OK`، `INSTALL_OK` و `DEPLOY_OK` گزارش شده است.
- تنظیمات خصوصی و کلید رمزنگاری قبلی حفظ شده‌اند؛ مهاجرت‌های `tradeplans.0002_tradeplan_origin_signal` و `trading.0001_initial` با `OK` اعمال شدند.
- PostgreSQL، Redis cache/broker/results همگی healthy؛ Workerهای orders/reports و Beat مستقل فعال و تست‌شده، Nginx configuration test موفق و مسیر readiness و login در origin محلی HTTP 200.
- اخطار `duplicate MIME type "text/html"` در فایل snippet مربوط به سایتی دیگر مشاهده شده، ولی در آزمون Nginx شکست ایجاد نکرده و بدون بررسی نباید فایل‌های دیگر سایت‌های VPS را تغییر داد.
- **سطح تأیید:** لاگ ترمینال ارسالی کاربر، نه آزمون مستقل اینترنت عمومی یا اجرای مسیر UI حساب اصلی. تکمیل API واقعی Binance و پذیرش مرورگر کاربر هنوز باز است.
- **مرز ریسک:** اجرای Stage08 فقط شبیه‌ساز Paper/Spot Long است؛ Position آزمایشی فعلاً فاقد سفارش حفاظتی خروج TP/SL و Trailing است، که در مراحل S09/S10 اضافه می‌شود؛ فعال‌سازی معامله واقعی ممنوع است.
