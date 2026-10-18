# پذیرش Alerts، Reports و رابط — Stage20

هشدار عمومی و هشدار وابسته به معامله از قیمت و مبنای ثابت ثبت‌شده ارزیابی می‌شوند. عبور تازه، cooldown و hysteresis مانع اعلان تکراری ناخواسته است. اعلان in-app/browser رسید خواندن دارد و بسته‌شدن معامله هشدار مرتبط را غیرفعال می‌کند؛ Alert هیچ سفارش یا تغییری در معامله ایجاد نمی‌کند.

گزارش فقط از Fill، fee و finance ledger ساخته می‌شود. Gross، fee، بهره و Net با Decimal محاسبه می‌شوند و هزینهٔ نامعلوم صفر فرض نمی‌شود. API و صفحه گزارش منطقه زمانی حساب را صریح نمایش می‌دهند؛ مرز روز/هفته/ماه با همان timezone ساخته می‌شود. CSV و SVG از همان dataset استفاده می‌کنند.

پذیرش مرورگر صفحات Login، Dashboard، Watchlist، Manual، Smart Paste، Inbox، Trades/History، Trade Details، Alerts، Notifications، Reports، Exchange، Operations، Profile، Security و System را در عرض‌های ۳۲۰، ۳۹۰، ۷۶۸ و دسکتاپ بررسی می‌کند. service worker فقط static عمومی را cache می‌کند و پاسخ خصوصی یا POST آفلاین replay نمی‌شود.
