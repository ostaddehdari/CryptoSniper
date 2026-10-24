# گزارش استیج ۲۴ — Live Charts و Unified Trade Workspace

تاریخ: ۲۴ اکتبر ۲۰۲۶  
نسخه منبع: 0.24.0rc1

## نتیجه

### W01 — Live Candles
API جدید chart داده OHLC را برای بازارهای owner-scoped برمی‌گرداند. 1m و 5m به intervalهای تاریخچه اضافه شده‌اند. Workspace هر ۱۵ ثانیه چارت انتخاب‌شده را تازه می‌کند.

### W02 — Overlay
سطوح Entry/TP/SL به‌عنوان سطح قیمت و رخداد لمس/تحقق به‌عنوان زمان نمایش داده می‌شوند. برای رخدادها خط عمودی و دایره رنگی رسم می‌شود تا سطح قیمت و زمان وقوع با هم اشتباه نشوند.

### W03 — Inbox / NewTrade / Trades
`/app/` اکنون یک shell رسمی در Repository دارد. Inbox دارای Card/Table و دو شماتیک Detail/Card است. NewTrade چارت بازار را بدون overlay معاملات قبلی نمایش می‌دهد. Trades داخلی و خارجی را در یک View جمع می‌کند.

### W04 — Archive / Refresh
Archive نرم به Signal، Trade، LiveSpotOrder و ExternalObservation اضافه شده است. سیگنال Expired خودکار archive می‌شود. Refresh جدید صرفاً reload صفحه نیست؛ اطلاعات حساب و External observations را از مرز read-only دوباره sync می‌کند و سپس لیست را بازسازی می‌کند.

### W05 — Verification
تست‌های Stage24 مسیرهای shell، archive filters، auto-archive، unified internal/external trades، read-sync refresh و candle/overlay را پوشش می‌دهند. نتیجه CI exact-source و بسته نصب پس از تثبیت commit نهایی در `docs/progress.json` ثبت می‌شود.

## مرز ادعا
- Refresh به معنی اجازه معامله واقعی نیست.
- `LIVE_TRADING_ENABLED=false` همچنان پیش‌فرض است.
- داده کندل عمومی برای نمایش/شواهد است؛ تطابق اجرای provider واقعی بدون credential و پذیرش اپراتور ادعا نمی‌شود.
- نصب VPS و مشاهده UI روی مرورگر احراز‌شده مرحله پذیرش جداگانه است.
