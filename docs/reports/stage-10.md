# Stage10 — Trailing SL/TP و Percentage Trailing | v0.10.0rc1

تاریخ: ۱۶ اکتبر ۲۰۲۶ | وضعیت در حال آزمون (partial)

| ورک | اجرا |
|---|---|
| W01 | دو Toggle مستقل Step/Percentage و تقدم Percentage از لحظه فعال‌سازی؛ Stop هرگز ضعیف‌تر نمی‌شود |
| W02 | فرمول Decimal: Long بیشترین قیمت × (۱−فاصله٪) و Short کمترین قیمت × (۱+فاصله٪)؛ Short فقط محاسبه، نه اجرا |
| W03 | Percentage از ابتدا: TPها نشانگر هستند، بدون TP sell؛ تغییر حین معامله فقط با reconciliation ledger در PAPER انجام می‌شود و cancellation نامعلوم پذیرفته نمی‌شود |
| W04 | ثبت high-water، قیمت و نسخه آخرین Tick در PostgreSQL؛ Worker دوره‌ای مستقل و وضعیت Feed قدیمی |
| W05 | کنترل‌های نسخه‌دار در UI، سناریوی قیمت دستی Paper، API خصوصی و آزمون بازگشت قیمت از بالای TP3 |

**مرز ایمنی:** فقط Simulator Spot Long. اجرای واقعی Binance و Margin/Short ممنوع است. TP/SL Native و لغو سفارش زنده خارج از این تحویل‌اند. سناریوی قیمت فقط داده ساختگی Paper می‌پذیرد.

وضعیت نهایی بعد از CI و استقرار کاربر با شواهد تکمیل می‌شود.

## آزمون‌های واقعی و انتشار تجمیعی ۱۶ اکتبر ۲۰۲۶

- [CI موفق نسخه ۰.۱۰](https://github.com/ostaddehdari/CryptoSniper/actions/runs/38959567887): commit `acde2adbe6a37d0ab875e7aff078beae4e7c6907`؛ **۸۶ تست Pytest موفق**، بدون شکست؛ Django check، migration drift، PostgreSQL، Redis، Celery Worker/Beat و Chromium desktop/mobile.
- سناریوی مرورگر: Smart Paste → Inbox → Trade Plan → Paper Worker → Position → فعال‌سازی سناریوی قیمت → high-water → برگشت ۱٪ → بسته‌شدن فقط یک‌باره Position؛ آزمون‌های جداگانه partial TP، حد ضرر، مقدار باقی‌مانده، tick تکراری، owner scope و تغییر قواعد Trailing نیز اجرا شدند.
- Artifact آزمون: `12071179939`.
- [GitHub Release تجمعی Stage09+10](https://github.com/ostaddehdari/CryptoSniper/releases/tag/stage10-v0.10.0rc1-deploy): سورس Stage01 تا Stage10 از commit آزموده‌شده.
- SHA256 ZIP: `d582c227dac0b7fb68a460c4a2e030e117460fd849a525813ee2e1007c311be8`؛ SHA256 Installer: `67844b2b4b7fff6c4ef24245078303c57949b9467ccd69de62532382f7627362`.
- **محدودیت:** نصب VPS کاربر هنوز تأیید نشده است؛ پذیرش رسمی S03/S04/S05 و اتصال واقعی Binance باز هستند. وضعیت `partial` به همین دلیل حفظ شده است.

**هشدار عملیاتی:** محافظت در این نسخه کاملاً شبیه‌سازی‌شده و زیر کنترل Worker است؛ قطع Worker، قطع فید، جهش قیمت و latency ریسک دارند. هیچ سفارش Stop واقعی در Binance وجود ندارد. Formula محاسبات Short آزمایش شده ولی ورود/خروج Short یا Margin اجرا نمی‌شود.
