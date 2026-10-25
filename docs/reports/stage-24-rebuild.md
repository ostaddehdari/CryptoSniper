# گزارش Stage 24 Rebuild

تاریخ: 24 اکتبر 2026  
نسخه: 0.24.0rc2

این Stage از روی Stage23 بازسازی شده و UI Stage24 قبلی را به ارث نمی‌برد.

## خروجی‌ها
- Workspace راست‌چین با Sidebar ثابت و هدر خلوت.
- ticker زنده USDT/USD و USDT/تومان در هدر.
- حذف کامل navigation تکراری از هدر.
- Live candle chart برای Inbox و NewTrade.
- overlay سطوح Signal/Trade و marker زمانی.
- Card/Table برای Signal.
- archive خودکار Signal منقضی.
- unified trade list برای Internal/Live/External.
- soft archive معاملات و فیلتر Active/Archive/All.
- refresh واقعی read-only حساب‌ها.

## مرز ایمنی
- چارت و ticker صرفاً display-only هستند.
- Refresh مجوز اجرای معامله واقعی ایجاد نمی‌کند.
- Live write همچنان با feature gate خاموش است.
