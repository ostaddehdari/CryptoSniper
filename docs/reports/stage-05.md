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

## آزمون‌های اجراشده و شواهد انتشار

- [CI تأییدشده 38931145676](https://github.com/ostaddehdari/CryptoSniper/actions/runs/38931145676): `success` برای commit `156018079c4a85c0079bf12643973f439f05786e`.
- تعداد آزمون‌ها: **۶۱ تست Pytest موفق**، هیچ failure؛ Ruff lint/format، Django check، عدم اختلاف migration، migrations روی PostgreSQL، Redis، Worker orders/reports/maintenance، Beat و مرورگر Chromium موفق.
- مسیر مرورگر: ساخت حساب شبیه‌ساز، `/manual/new/`، ایجاد Draft، تأیید snapshot، صفحهٔ موبایل ۳۲۰/۳۹۰/۷۶۸، نبود overflow و خطای JS.
- شواهد artifact شناسه `12059695340` از همان CI.
- [GitHub Release نسخه آزمایشی Stage05](https://github.com/ostaddehdari/CryptoSniper/releases/tag/stage05-v0.5.0rc1-deploy) فایل ZIP تجمعی و نصب‌کننده با تأیید `--check` دارد.
- SHA-256 ZIP: `5f1a5f3a41b66ca3a552e0515414685b0b67e7cc01a6c9a957ee638895872d15`.
- SHA-256 installer: `b9e2bf263a9676302e802e8133225716349eb2095014521dcadeff15ff2696e2`.

## وضعیت تحویل و قیدهای مانده

تمام پنج ورک Stage05 از نظر کد و CI اجرا شده‌اند. با این‌حال تا رفع موارد بالادستی (آزمون حساب واقعی Binance و موارد باقی‌مانده S04) و **تأیید استقرار Stage05 روی VPS کاربر**، Stage05 به‌طور رسمی `partial` باقی می‌ماند. تست مرورگر CI با شبیه‌ساز است و به معنای معامله یا تست Binance واقعی نیست. هیچ سفارش واقعی یا order request در Stage05 ارسال نمی‌شود.

## تأیید استقرار VPS توسط کاربر — ۱۶ اکتبر ۲۰۲۶

شواهد این بخش از خروجی ترمینال **ارسالی کاربر** از Ubuntu 24.04 روی میزبان `5.61.27.185` استخراج شده‌اند و به معنی دسترسی مستقل به سرور نیستند.

- دستور رسمی `scripts/deploy.sh` نسخهٔ `stage05-v0.5.0rc1-deploy` را دانلود و هر دو SHA-256 را موفق تطبیق داده است.
- `CHECK_OK` برای ZIP تجمیعی Stage05 دریافت شده؛ نصب با حفظ تنظیمات خصوصی و کلید رمزنگاری ادامه یافته است.
- `tradeplans.0001_initial` روی PostgreSQL واقعی سرور با `OK` اعمال شد؛ فایل‌های static هم جمع‌آوری شدند.
- `/health/ready/`: PostgreSQL، Redis cache، broker و result backend همگی `true`؛ Workerهای مستقل Orders/Reports و heartbeat Beat موفق، سرویس‌های web/orders/reports/beat/redis فعال.
- Nginx syntax test موفق؛ HTTPS **origin محلی** برای readiness و login هر دو HTTP 200 داد.
- خروجی نهایی نصب‌کننده: `INSTALL_OK: CryptoSniper Stage05 v0.5.0rc1` و `DEPLOY_OK`.
- اخطار `duplicate MIME type "text/html"` در snippet متعلق به سرویس دیگری ثبت شده؛ آزمون Nginx را خراب نکرده و در این استیج تغییر داده نشده است.

**نتیجه:** استقرار Stage05 از نظر خروجی نصب‌کننده روی سرور کاربر موفق است. تست دستی سناریوی معامله در مرورگر عمومی و آزمون credentials واقعی Binance هنوز به تأیید مجزا نیاز دارند. وضعیت S03/S04/S05 با وجود این استقرار فعلاً `partial` می‌ماند و ارسال سفارش واقعی همچنان مسدود است.
