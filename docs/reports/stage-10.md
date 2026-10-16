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
