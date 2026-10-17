# استیج ۱۱ — پردازش پس‌زمینه، بازیابی و تطبیق | 0.12.0rc1

وضعیت: partial؛ پیاده‌سازی پنج ورک برای Paper Spot Long، CI نهایی موفق؛ پذیرش نصب نسخهٔ جدید روی VPS هنوز باز است. درخواست صریح کاربر اجرای هم‌زمان S11 و S12 را مجاز کرد. اتصال حساب واقعی Binance در S03 همچنان تأیید نشده است.

| ورک | نتیجه |
|---|---|
| S11-W01 | هفت صف مستقل signals/orders/market_data/trailing/alerts/reports/maintenance؛ Worker مستقل برای هر صف در نصب‌کننده و smoke؛ Beat با Redis lease و heartbeat واقعی هر صف |
| S11-W02 | intent/outbox پیش از ارسال؛ دفتر provider شبیه‌ساز در PostgreSQL با account+client ID یکتا؛ lease با آزادسازی token-aware؛ قفل ردیفی و fence پایدار برای جلوگیری از ثبت نتیجهٔ Worker قدیمی |
| S11-W03 | lookup دفتر provider پیش از retry؛ backoff نمایی تا ۳۰۰ ثانیه و jitter، سقف پنج تلاش؛ خطای دائمی dead-letter؛ مسیر UI بازیابی نتیجه یا بستن کار شکست‌خورده فقط در Paper و بدون fill |
| S11-W04 | بازیابی receipt گم‌شده، محاسبه Order/Position/Trade از ledger ورود/خروج و کارمزد، بررسی رزرو مقابل موجودی؛ توقف ورود جدید در اختلاف حساس؛ Binance Spot observations فقط GET و بدون مدیریت خودکار External Trade |
| S11-W05 | مرکز عملیات، heartbeat/queue lag/قدیمی‌ترین outbox/feed lag/last sync؛ pause/resume با version؛ resume فقط پس از تطبیق تازه و بدون اختلاف باز؛ runbook زیر |

## محدوده و محدودیت واقعی

- هیچ سفارش واقعی، Margin/Short یا انتقال مدیریت معامله خارجی فعال نشده است. مشاهدهٔ خارجی با برچسب زمان دریافت نمایش داده می‌شود؛ دادهٔ تاریخی به معنای وضعیت زنده یا هزینه ورود شناخته‌شده نیست.
- Binance بدون حساب مجاز آزمایش نشده است. قرارداد read-only با transport ساختگی آزمایش می‌شود و جای اتصال واقعی را نمی‌گیرد. تاریخچه محدود به چهار نماد نخست واچ‌لیست و ۱۰۰ fill اخیر هرکدام است؛ تضمین بازیابی تمام تاریخچه یا Margin وجود ندارد.
- دفتر Paper provider و engine در دو تراکنش جدا ثبت می‌شوند؛ این provider شبیه‌ساز است، نه صرافی خارجی. نتیجهٔ نامعلوم live هرگز کورکورانه retry نمی‌شود.
- قفل Redis تضمین تصمیم مالی نیست؛ مرجع PostgreSQL و uniqueness/fence است. در قطع DB/Redis کار جدید باید متوقف شود؛ خروج حفاظتی همچنان به Worker و feed وابسته است. این نسخه Stop بومی در Binance ندارد.
- صف signals تنها زیرساخت عمومی است؛ هیچ Telegram/Telethon/AI پیش از S21 افزوده نشده است.
- پردازش دوره‌ای bounded است (حداکثر ۵۰ حساب و ۱۰۰۰ معامله در هر حساب در هر اجرای recovery)؛ مقیاس بالاتر نیازمند partition/cursor گسترده‌تر است.

## Runbook

۱. در مرکز عملیات حساب را برای «ورود جدید» متوقف کنید؛ خروج‌های حفاظتی فعال می‌مانند. قطع Worker حفاظتی برای توقف ورود مجاز نیست.
۲. وضعیت PostgreSQL، Redis و هفت Worker را بررسی کنید. صف reports پردازش سفارش/Trailing را مسدود نمی‌کند. Beat تنها با lease فعال منتشر می‌کند؛ وظایف مالی در برابر تکرار تحویل idempotent هستند.
۳. «تطبیق حساب» را اجرا کنید. receipt موجود بازیابی می‌شود؛ high-water و effective-stop از DB حفظ می‌شوند و به مقدار ضعیف‌تر بازنشانی نمی‌شوند. اختلاف ناشناخته حساب را متوقف نگه می‌دارد.
۴. در dead-letter فقط نتیجهٔ provider موجود را بازیابی کنید، یا اگر هیچ fill/receipt وجود ندارد، از کنترل Paper برای بستن کار شکست‌خورده استفاده کنید؛ صرف دیدن timeout مجوز ارسال دوباره نیست.
۵. پس از رفع علت و تطبیق تازه، «ادامه پس از تطبیق» را اجرا کنید. این کنترل هیچ مجوز live نمی‌دهد.

```bash
systemctl status cryptosniper-{web,orders,reports,beat,signals,market-data,trailing,alerts,maintenance,redis}
journalctl -u cryptosniper-orders -u cryptosniper-trailing -u cryptosniper-maintenance --since '-15 min'
```

از چاپ env، کلیدها، URL امضاشده یا فایل ورود در گزارش عمومی خودداری کنید. نصب‌کننده تعریف unitهای قبلی و تنظیمات Nginx را پشتیبان می‌گیرد؛ rollback فایل برنامه با migration معکوس مخرب همراه نیست (migrationهای این نسخه افزایشی‌اند).

## بررسی‌ها

آزمون‌ها شامل PostgreSQL واقعی و دو Thread با اتصال جدا، Redis lease، crash-injection پس از ثبت provider receipt، timeout-injection با نتیجهٔ ثبت‌شده، fence قدیمی، backoff/dead-letter، repair ledger، توقف/ادامه، owner scope و اتصال واقعاً ناموجود Redis هستند. هیچ failure-injection ادعای آزمایش حساب واقعی Binance ندارد. نتیجهٔ نهایی CI در بخش شواهد انتشار ثبت می‌شود.

## شواهد نهایی و انتشار

- [CI منبع دقیق](https://github.com/ostaddehdari/CryptoSniper/actions/runs/39019031643): commit `21b8b520466b1c7e76b495bbbfefa81f24b8371e`؛ **۱۱۰ تست موفق** در PostgreSQL واقعی، Redis، هفت Worker، Beat و Chromium.
- سناریوی کامل UI هشدار، ثبت اعلان بعد از بستن صفحه، read receipt، موبایل/دسکتاپ و نبود overflow/خطای JS موفق بود. artifact: `12096156612`.
- [انتشار تجمعی 0.12.0rc1](https://github.com/ostaddehdari/CryptoSniper/releases/tag/stage12-v0.12.0rc1-deploy)، [ساخت و CHECK_OK نصب‌کننده](https://github.com/ostaddehdari/CryptoSniper/actions/runs/39019202911).
- ZIP SHA256: `71d3f3b9e789990a69e4680ddc726103c5d358bf2e2edd722540d210b8e9d7d1`؛ Installer SHA256: `cc1670dbacffab78408bafc1c44d516d8489c46844f7563e110cb0af62e3be2a`.
- آخرین نصب تأییدشدهٔ VPS طبق لاگ کاربر 0.10.0rc1 است؛ نصب 0.12 روی VPS هنوز انجام/تأیید نشده است.
