# استیج ۱۵ — گزارش‌ها، محاسبات و نمودارها | 0.16.0rc1

هر پنج ورک گزارش برای معاملات مالک پیاده‌سازی شده‌اند. دامنهٔ تأییدشده Paper Spot Long است؛ دادهٔ Margin می‌تواند هزینهٔ وام/بازپرداخت را ثبت و گزارش کند، اما اجرای واقعی Margin و سفارش‌نویسی Binance همچنان غیرفعال است.

| ورک | نتیجه |
|---|---|
| S15-W01 | محاسبه Decimal برای gross/net realized P/L، کارمزد ورود و خروج، تبدیل fee asset با نرخ ثبت‌شده، بهرهٔ وام و repayment؛ مقدار فاقد نرخ لازم به‌صراحت unknown است و صفر حدس زده نمی‌شود. |
| S15-W02 | total/win/loss/breakeven/unknown، میانگین سود/زیان، بهترین/بدترین و مدت؛ breakeven با بازهٔ ثابت `±0.00000001` و مخرج win rate فقط `wins + losses`. |
| S15-W03 | aggregate روز/هفته/ماه و تفکیک total/coin/exchange/source بر اساس timezone کاربر؛ اجرای دوباره با `update_or_create` عددها را دو بار نمی‌شمارد. |
| S15-W04 | مرکز گزارش، فیلتر تاریخ و dimension، نمودار SVG سمت سرور و CSV یکسان با dataset؛ سلول‌های خطرناک CSV برای جلوگیری از formula injection خنثی می‌شوند. |
| S15-W05 | versioned cache، invalidation با تغییر Trade/Fill/Exit/Finance، rebuild مستقل در صف reports و drill-down به معاملات مالک. |

## قرارداد محاسبات

مقادیر مالی از Decimal و ledger ثبت‌شده ساخته می‌شوند؛ float وارد محاسبات پولی نمی‌شود. `gross = proceeds - cost basis` و `net = gross - entry fees - exit fees - finance interest` است. کارمزد quote مستقیم استفاده می‌شود؛ کارمزد دارایی دیگر فقط با `fee_quote_rate` ثبت‌شده تبدیل می‌شود. نبود این نرخ یا دادهٔ لازم، نتیجه را unknown می‌کند تا گزارش سود کاذب نسازد. رویداد repayment اصل بدهی را ثبت می‌کند و هزینه محسوب نمی‌شود؛ interest هزینه است.

روز/هفته/ماه با timezone حساب مرزبندی می‌شود و مقدار UTC پایگاه داده تنها منبع زمان است. گزارش بازهٔ زمانی و خروجی CSV/SVG از یک dataset استفاده می‌کنند. کار اصلاحی reconciliation نسخهٔ گزارش را dirty می‌کند؛ Worker گزارش جدا از orders آن را بازسازی می‌کند.

## شواهد و محدودیت‌ها

- اجرای اولیه CI روی commit `57c19e1e289cd997ffe821ec454a453b7d2e680b`: **۱۴۹ تست**، migration واقعی PostgreSQL، Redis، هفت Worker و Beat موفق؛ مرحلهٔ browser یک خطای JavaScript در محافظ آفلاین Stage16 پیدا کرد که در commit `e1d376b75b329d8b80016da17a4811951faf0a59` رفع و با regression test پوشش داده شد.
- [CI موفق پس از اصلاح](https://github.com/ostaddehdari/CryptoSniper/actions/runs/39055497955): **۱۵۰ تست**، schema/lint/migration، PostgreSQL/Redis، هفت Worker/Beat و Chromium؛ artifact شواهد `12109002649`.
- checksumهای Release پس از انتشار در `docs/progress.json` ثبت می‌شوند.
- پذیرش حجم بزرگ تاریخچه، نصب Stage16 روی VPS و مرورگر عمومی هنوز باز است. Binance واقعی و اجرای Margin/Short در این نسخه تأیید نشده‌اند.

