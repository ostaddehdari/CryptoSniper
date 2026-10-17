# استیج ۱۲ — Price Alert و اعلان‌ها | 0.12.0rc1

وضعیت: partial به دلیل پذیرش باز رابط عمومی VPS و پیش‌نیاز حساب واقعی Binance؛ پنج ورک در محدوده Paper و هشدار عمومی پیاده شده‌اند. هشدار تنها اطلاع‌رسانی می‌کند و هیچ خرید، فروش، لغو سفارش یا تغییر معامله‌ای انجام نمی‌دهد.

| ورک | نتیجه |
|---|---|
| S12-W01 | هشدار مستقل یا مرتبط با معامله، قیمت، افزایش/کاهش درصدی، reference price/time/source ثابت؛ مالکیت و optimistic version |
| S12-W02 | تشخیص عبور، timestamp یکنواخت، جلوگیری از tick تکراری، رد feed قدیمی/آینده، one-shot/repeat، hysteresis و cooldown؛ Worker مستقل alerts |
| S12-W03 | سود خالص Paper پس از fees، درصد نسبت میانگین Entry، فاصلهٔ دقیق SL مؤثر و Percentage activation/stop؛ خاموشی هشدار معامله بسته |
| S12-W04 | Notification مرکزی، ترجیحات in-app/browser، unread/read receipt؛ درخواست رضایت مرورگر تنها با کلیک، claim تراکنشی و بدون انتشار دادهٔ کاربران دیگر |
| S12-W05 | ساخت/ویرایش/خاموشی/بازفعال‌سازی، API خصوصی و CSRF، میان‌بر صفحه معامله و واچ‌لیست، تعداد هشدار فعال و نشانگر اعلان top bar؛ صفحه موبایل و دسکتاپ |

## تعریف محاسبه

- ذخیره/ویرایش هشدار مبنای تازه‌ای از feed یا Paper scenario ذخیره می‌کند؛ reference بعد از ذخیره خودکار جابه‌جا نمی‌شود. قیمت اولیه در سوی فعال آستانه، تا عبور تازه اعلان نمی‌سازد.
- rise/fall جهت را از نوع می‌گیرند. Price/profit/Entry از جهت above/below استفاده می‌کنند. proximity یعنی abs(price-level)/level × 100 ≤ threshold.
- hysteresis برای Price درصد آستانه و برای metric درصدی واحد درصد است. تکرار فقط پس از بازآماده‌سازی خارج از حاشیه و رعایت cooldown رخ می‌دهد. زمان/provider Tick تکراری هیچ event تازه‌ای نمی‌سازد.
- سود = (درآمد خروج‌های اجراشده + ارزش باقی‌مانده با قیمت فعلی − ارزش واقعی ورود − همه fees پرداخت‌شده − برآورد fee خروج باقی‌مانده) / ارزش واقعی ورود × ۱۰۰. مبنا و اجزا در AlertEvent ثبت می‌شوند. در Spot Paper بهره قرض صفر به دلیل نبود قرض است؛ Margin/live با بهره یا هزینه نامعلوم پشتیبانی نمی‌شود.
- نزدیک activation فقط تا قبل از فعال شدن Percentage معنی دارد؛ نزدیک stop فقط پس از فعال شدن Percentage. نبود مبنای محاسبه با waiting_for_basis نمایش داده می‌شود.

## مرورگر و دوام

بستن مرورگر پایش Worker و ثبت event/notification در DB را قطع نمی‌کند. نمایش browser notification نیازمند HTTPS، اجازه مرورگر، ترجیح browser روشن و صفحهٔ باز است؛ Web Push/اعلان تضمینی سیستم‌عامل در حالت بسته در این نسخه وجود ندارد. رد اجازه مرورگر اعلان in-app را خراب نمی‌کند. claim مرورگر at-most-once است؛ crash مرورگر پس از claim ممکن است نمایش سیستم‌عامل را از دست بدهد، اما اعلان in-app باقی است. تنظیم in-app خاموش آن اعلان را از فهرست محصول حذف می‌کند؛ رویداد audit همچنان ثبت می‌شود.

## بررسی‌ها

آستانه/دو جهت/درصد ثابت، hysteresis، تکرار Tick، feed قدیمی، سود بعد fee، هر سه proximity، معامله بسته، owner isolation، CSRF، version و worker بدون مرورگر با PostgreSQL/Redis آزمایش می‌شوند. smoke رابط روی عرض‌های ۳۲۰/۳۹۰/۷۶۸ و دسکتاپ ساخت rule، دریافت بعد از بستن صفحه و read receipt را بررسی می‌کند. شواهد نهایی CI در بخش انتشار اضافه می‌شود.

## شواهد نهایی و انتشار

- [CI منبع دقیق](https://github.com/ostaddehdari/CryptoSniper/actions/runs/39019031643): commit `21b8b520466b1c7e76b495bbbfefa81f24b8371e`؛ **۱۱۰ تست موفق** در PostgreSQL واقعی، Redis، هفت Worker، Beat و Chromium.
- سناریوی کامل UI هشدار، ثبت اعلان بعد از بستن صفحه، read receipt، موبایل/دسکتاپ و نبود overflow/خطای JS موفق بود. artifact: `12096156612`.
- [انتشار تجمعی 0.12.0rc1](https://github.com/ostaddehdari/CryptoSniper/releases/tag/stage12-v0.12.0rc1-deploy)، [ساخت و CHECK_OK نصب‌کننده](https://github.com/ostaddehdari/CryptoSniper/actions/runs/39019202911).
- ZIP SHA256: `71d3f3b9e789990a69e4680ddc726103c5d358bf2e2edd722540d210b8e9d7d1`؛ Installer SHA256: `cc1670dbacffab78408bafc1c44d516d8489c46844f7563e110cb0af62e3be2a`.
- لاگ اپراتور در ۱۷ اکتبر ۲۰۲۶ ساعت ۱۵:۱۱ UTC نصب موفق Stage12 نسخه 0.12.0rc1 با r1 را تأیید کرد؛ کلید و ورود حفظ، migrationها اجرا، هفت Worker فعال و readiness/login از Nginx محلی HTTP 200 بودند. این شواهد نصب است؛ پذیرش مرورگر عمومی و حساب واقعی Binance جداگانه باز است.

## اصلاح نصب‌کننده r1 — ۱۷ اکتبر ۲۰۲۶

لاگ کاربر نشان داد ارتقا از 0.10 در مرحلهٔ بررسی Nginx با پیام unmanaged متوقف شد؛ برنامه و دیتابیس در این اجرا تعویض نشدند. علت، جاافتادن Stage10 در KNOWN_MARKERS نصب‌کنندهٔ Stage12 بود. اصلاح r1 همهٔ headerهای دقیق Stage01 تا Stage12 را می‌پذیرد و فایل ناشناس یا تغییر هم‌زمان فایل را همچنان رد می‌کند. هیچ راهکار حذف snippet یا دورزدن تشخیص مالکیت به کاربر داده نشد.

[انتشار r1](https://github.com/ostaddehdari/CryptoSniper/releases/tag/stage12-v0.12.0rc1-deploy-r1) · [شش تست regression و CHECK_OK بسته](https://github.com/ostaddehdari/CryptoSniper/actions/runs/39041880098). ZIP همان source قبلاً آزموده‌شده است؛ SHA256 نصب‌کننده جدید: `c2991fddebd65de18a1673f34f758f774e5fb042d2257e15f1a5ed3395c76740`. نصب مجدد VPS با r1 در لاگ واقعی بعدی کاربر (۱۵:۱۱ UTC) با INSTALL_OK و DEPLOY_OK تأیید شد.
