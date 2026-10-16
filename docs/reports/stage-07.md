# Stage 07 — Smart Paste v0.8.0rc1

پنج ورک S07-W01..05 در GitHub کدنویسی شده است: Normalization مستقل (بدون تغییر Raw)، Rule Parser نسخه‌دار، استخراج Pair/Side/Entry یا Range/SL/Leverage و همه TPها، هشدار ابهام و Confidence فنی، رابط Smart Paste و مسیر بازبینی در Inbox. شش هدف OP در metadata حفظ و تنها سه هدف اول برای ساختار معاملات لحاظ می‌شوند.

**مرز امنیتی:** Futures به Spot/Margin تبدیل نمی‌شود؛ Missing SL یا Entry Range به بازبینی دستی نیاز دارد. Trailing پیش‌فرض هر دو روشن، trigger=TP1، distance=1٪، اما اجرای منطق trailing تا S09/S10 پیاده نشده است. هیچ Telethon یا AI پیش از S21 فعال نیست.

**وضعیت:** partial تا CI موفق و نصب تأییدشده VPS؛ همچنین الزامات باقی‌مانده استیج‌های قبلی.

## شواهد نهایی آزمایش و انتشار ۱۶ اکتبر ۲۰۲۶

- [GitHub CI #38954065804](https://github.com/ostaddehdari/CryptoSniper/actions/runs/38954065804) موفق؛ **۷۶ آزمون Pytest موفق** روی PostgreSQL واقعی، Redis، Celery Worker/Beat و Smoke مرورگر Chromium (دسکتاپ/موبایل).
- کد تست‌شده Release: `04d84c0e5ef75155bce32a173c2441e20f0f5080`؛ [انتشار تجمعی Stage07+08](https://github.com/ostaddehdari/CryptoSniper/releases/tag/stage08-v0.8.0rc1-deploy).
- ZIP SHA256: `24a5ff7a700b2c56cca80af10681617bb1a8f22b9533757bc6fe8c2e2ad14fbd`، نصب‌کننده SHA256: `43604c51082bc1341b608d069a3185761126d54e0b13a1f458b7ae07a20671cd`.
- آزمون کامل Smart Paste→Inbox→Trade Plan→Paper→Worker→Position اجرا شده و مرورگر پس از ثبت سفارش آزمایشی می‌تواند بسته شود؛ وابستگی به جلسه مرورگر وجود ندارد.
- استقرار روی VPS کاربر هنوز انجام نشده و آزمون واقعی Binance S03-W04 باز است. وضعیت رسمی تا پذیرش همه پیش‌نیازها **partial** باقی می‌ماند.
