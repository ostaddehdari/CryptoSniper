# Stage 24 — Rebuild روی پایه Stage 23

مبنای سورس: آخرین Stage23 سالم `657071e06c6f08b67298835972a153f8f547bc81`.

## اصل طراحی
- UI قبلی Stage24 مبنا نیست و assetهای `stage24-app.css/js` استفاده نمی‌شوند.
- Workspace رسمی با assetهای مستقل `stage24-rebuild.css/js` ساخته می‌شود.
- ناوبری فقط در Sidebar است؛ هدر هیچ دکمه ناوبری تکراری ندارد.
- هدر فقط وضعیت Live و قیمت USDT/USD و USDT/تومان را نشان می‌دهد.

## W01 — Live Chart
- کندل‌های 1m/5m/15m/1h/4h.
- Inbox: Entry/TP1/TP2/TP3/SL به‌صورت سطح قیمت.
- زمان برخورد هر سطح: خط عمودی و marker دایره‌ای.
- NewTrade: هیچ overlay از معاملات باز قبلی ندارد.

## W02 — Signal UI
- Card/Table.
- شماتیک کوچک در Card.
- شماتیک کامل در Detail.
- Active / Archive / All.
- Expired به‌صورت خودکار Archive می‌شود.

## W03 — Trade UI
- Paper + Live + External در یک فهرست.
- انتخاب معامله، Entry/TP/SL و markerهای ورود/خروج را روی نمودار نشان می‌دهد.
- Archive به‌جای delete واقعی.
- Active / Archive / All.

## W04 — Real Refresh
- Refresh یک read-sync واقعی روی حساب‌های متصل اجرا می‌کند.
- External observations پس از sync دوباره خوانده می‌شوند.
- هیچ Live write با Refresh فعال نمی‌شود.

## W05 — Header Ticker و تحویل
- USDT/USD از Binance public.
- USDT/تومان از Nobitex public.
- cache کوتاه و fallback stale.
- نسخه: 0.24.0rc2.
