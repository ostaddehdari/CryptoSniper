# گزارش پیاده‌سازی Stage 05 — 0.5.0rc1

تاریخ: ۱۶ اکتبر ۲۰۲۶ | وضعیت: `partial` تا آزمون‌های نسخهٔ نهایی و استقرار کاربر؛ پیش‌نیازهای S03/S04 هم هنوز کامل نشده‌اند.

## پوشش پنج ورک
- **S05-W01** فرم RTL موبایل‌محور ورود دستی: حساب صرافی، pair، spot/margin، long/short، Entry، TP1/2/3، SL، مبلغ سرمایه، leverage، two trailing switches؛ بدون ورود مستقل quantity.
- **S05-W02** محاسبات صرفاً Decimal: ترتیب اهداف بر حسب جهت، tick، lot rounding down، min notional، موجودی آزاد ۱۵ دقیقه اخیر، estimated fee و collateral. Spot فقط long و leverage=1؛ Margin با permission و leverage بازار.
- **S05-W03** API خصوصی context برای quote/time/price-distance/free balance/limit و JS وابسته به انتخاب Account/Market؛ داده قیمت display-only است.
- **S05-W04** مدل PostgreSQL TradePlan و immutable approved snapshot، lifecycle draft/ready با کنترل revision و تراکنش DB؛ confirmation هیچ سفارش واقعی ایجاد نمی‌کند.
- **S05-W05** GET pages، POST save/edit/confirm، REST JSON create/edit/confirm/detail، idempotency مبتنی بر owner+UUID و hash، تست DB/مالکیت/بدون سفارش و smoke مرورگر.

## مرزهای امنیتی
- API صرافی برای سفارش فراخوانده نمی‌شود؛ qty فقط برای preview است.
- مقدارهای fee و exit fee تخمینی‌اند؛ به P&L قطعی تبدیل نشوند.
- Pending credentials Binance یا فقدان داده تازه سبب رد preview-ready می‌شود؛ هیچ تبدیل خودکار futures/margin انجام نمی‌شود.
- وضعیت upstream: S03-W04 آزمون Provider واقعی نیازمند credential مجاز داخل سرور است و S04 هنوز بخشی از پذیرش UI را ندارد.
