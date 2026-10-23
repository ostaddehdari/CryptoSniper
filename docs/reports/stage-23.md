# گزارش استیج ۲۳ — تثبیت معامله و UI عملیاتی

تاریخ: ۲۳ اکتبر ۲۰۲۶  
نسخه منبع: 0.23.0rc1

## نتیجه پنج Work

### W01 — Manual Trade و Trailing
جست‌وجوی بازار اکنون نتیجه قابل انتخاب می‌سازد و انتخاب، مقدار واقعی select را تغییر می‌دهد. Entry معامله تازه از draft قبلی بازیابی نمی‌شود. تنظیمات مبلغ/درصدهای TP/فاصله Trailing در UI integer هستند. Trigger درصدی TP1/TP2/TP3 در snapshot و موتور حفظ می‌شود. Trailing SL دیگر پله‌ای نیست و فقط با TP1 یک‌بار Stop را به Entry می‌آورد.

### W02 — External Trade
External observation برای adapterهای Spot واقعی تعمیم داده شد. فهرست و جزئیات شامل داده‌های معامله و تاریخچه هستند. مدیریت External نیازمند adoption صریح کاربر، Spot Long، حجم باقی‌مانده تأییدشده، بازار فعال، موجودی کافی و Live gate است. سیستم عمداً cost basis/remaining position را از یک Fill حدس نمی‌زند.

### W03 — Signal Inbox / Analytics
Trash واقعی به‌صورت trashed_at و قابل restore اضافه شد؛ bulk trash/restore وجود دارد. دکمه «تأیید و انتقال به معامله» transition و redirect را در یک جریان انجام می‌دهد. Analytics کانال علاوه بر win rate، evaluation coverage، ambiguous/no-data/not-triggered/open و confidence را نمایش می‌دهد.

### W04 — Exchange / Order operations
Add Exchange و sync/submit در خطای Broker fail gracefully می‌شوند. اتصال Disable/Revoked در فهرست فعال و System Status نمایش داده نمی‌شود. queue_live_spot_order و executor مستقلاً Read+Spot، Withdrawal=false، market type، lot/tick، min/max/notional و freshness/کفایت balance را بررسی می‌کنند. Receipt provider نیز قبل از ثبت نتیجه اعتبارسنجی می‌شود.

### W05 — Delivery
نسخه، roadmap/plan/progress، installer و release workflow برای Stage23 اضافه شدند. Release workflow قبل از ساخت asset منتظر CI موفق همان commit می‌ماند و سپس ZIP/installer/runlog/SHA256 می‌سازد.

## مرز ادعا
- کد Live Spot وجود دارد اما LIVE_TRADING_ENABLED=false پیش‌فرض است.
- در این گزارش موفقیت معامله واقعی هیچ provider ادعا نمی‌شود؛ credential واقعی و acceptance اپراتور ارائه نشده است.
- Historical Telegram import هیچ معامله‌ای ایجاد نمی‌کند.
- External management فقط پس از adoption صریح است و Fill را Position فرض نمی‌کند.
- نصب VPS و مرورگر عمومی باید با لاگ اپراتور ثبت شود.

## شواهد
Commitهای W01 تا W04 و fixهای CI در docs/progress.json ثبت شده‌اند. نتیجه exact-source CI و Release پس از اجرای GitHub Actions در همان فایل پین می‌شود.
