# گزارش اجرایی Stage 04 — v0.4.0rc1

تاریخ: ۱۶ اکتبر ۲۰۲۶ · وضعیت در حال آزمون / partial

## اجرا
- **S04-W01**: دریافت Price و Orderbook خواندنی از Simulator و Binance، بررسی Decimal و timestamp، کش Redis، Fresh/Stale، قفل جلوگیری از درخواست همزمان.
- **S04-W02**: جستجوی Coin/Pair فقط بین بازارهای قابل‌خواندن حساب‌های متصل همان کاربر؛ metadata مربوط به tick/lot/min-notional و زمان آخرین Sync.
- **S04-W03**: API خصوصی Search/Quotes، SSE مشروط به فعال‌سازی ASGI، fallback امن Polling در Gunicorn WSGI؛ حداکثر ۲۰ Market در درخواست.
- **S04-W04**: Watchlist/WatchlistItem در PostgreSQL با constraints و migration، ثبت/حذف و چند فهرست، نمایش بازار، قیمت، shortcutهای آینده بدون ساخت روش سیگنال جدید.
- **S04-W05**: Celery beat و Worker عمومی قیمت بدون API Secret، محدودیت batch و درخواست دستی، Backoff مرورگر، UI موبایل و desktop، تست‌های owner-scope/staleness و smoke مرورگر.

## مرزها و ریسک‌ها
1. دریافت قیمت Binance عمومی است و نیاز به API Key ندارد، ولی **اتصال واقعی حساب Binance در S03-W04 هنوز آزمایش نشده** است.
2. قیمت‌های تازه نیز صراحتاً `trade_eligible: false` دارند؛ این مرحله موتور اجرای سفارش ندارد.
3. تا زمان تأیید CI و آزمون استقرار سرور، **نباید استیج را done اعلام کرد**. تمام شواهد در گزارش نهایی پس از اجرا افزوده می‌شوند.
4. Quick Signal / Smart Paste صرفاً توضیح مرحلهٔ آینده‌اند؛ پیاده‌سازی S05/S07 هنوز شروع نشده.
5. حالت SSE صرفاً برای فرآیند ASGI قابل استفاده است؛ سرویس فعلی Gunicorn WSGI از polling کنترل‌شده استفاده می‌کند.

## نصب و انتشار
از GitHub Release اختصاصی Stage04 و `scripts/deploy.sh` با SHA256 پین‌شده استفاده شود. ZIP تجمیعی باید مراحل ۰۱ تا ۰۴ را شامل شود و تنظیمات خصوصی Stage03 را حفظ کند.
