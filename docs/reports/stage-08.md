# Stage 08 — موتور Paper و مدیریت Position v0.8.0rc1

پیاده‌سازی هر پنج ورک S08-W01..05: Trade/Order/Fill/Position، رویداد افزایشی و وضعیت‌های جداگانه، request_key UUID، client_order_id یکتا، outbox پایدار، Worker/Celery Beat و مسیر دستی یا SmartPaste→TradePlan→Paper. Snapshot تأییدشده مستقل از تنظیمات جدید کاربر باقی می‌ماند.

**کنترل ریسک:** فقط Spot Long روی Simulator داخلی Paper. درخواست Binance Live، Margin بدون borrow/repay تأییدشده و Futures/Perpetual رد می‌شوند. رزرو سرمایه در PostgreSQL با lock حساب و سقف تعداد/سرمایه؛ شناسه Fill یکتا از دوباره‌شماری جلوگیری می‌کند. بعد از timeout/crash حین ارسال، وضعیت UNCERTAIN ثبت می‌شود و هرگز بدون reconciliation دوباره ارسال نمی‌شود. تأیید مرورگر شرط اجرای Worker نیست.

**محدودیت:** Simulator نسخه نخست Market order را تماماً پر می‌کند؛ partial fill در لایه record_fill و تست پوشش داده شده است. سفارش TP/SL و Trailing هنوز وارد موتور نشده‌اند (S09/S10)؛ در این نسخه، اجرای Paper **بدون سفارش خروج محافظتی** است. برای حساب واقعی هرگز فعال نیست.

**وضعیت:** partial تا CI و تأیید نصب VPS، معیارهای رسمی قبلی و Binance واقعی.
