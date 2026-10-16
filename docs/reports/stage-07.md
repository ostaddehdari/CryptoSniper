# Stage 07 — Smart Paste v0.8.0rc1

پنج ورک S07-W01..05 در GitHub کدنویسی شده است: Normalization مستقل (بدون تغییر Raw)، Rule Parser نسخه‌دار، استخراج Pair/Side/Entry یا Range/SL/Leverage و همه TPها، هشدار ابهام و Confidence فنی، رابط Smart Paste و مسیر بازبینی در Inbox. شش هدف OP در metadata حفظ و تنها سه هدف اول برای ساختار معاملات لحاظ می‌شوند.

**مرز امنیتی:** Futures به Spot/Margin تبدیل نمی‌شود؛ Missing SL یا Entry Range به بازبینی دستی نیاز دارد. Trailing پیش‌فرض هر دو روشن، trigger=TP1، distance=1٪، اما اجرای منطق trailing تا S09/S10 پیاده نشده است. هیچ Telethon یا AI پیش از S21 فعال نیست.

**وضعیت:** partial تا CI موفق و نصب تأییدشده VPS؛ همچنین الزامات باقی‌مانده استیج‌های قبلی.
