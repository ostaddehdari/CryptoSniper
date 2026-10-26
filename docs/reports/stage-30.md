# Stage30 — معامله جدید و مدیریت ریسک

وضعیت: پنج ورک از نظر کد و آزمون تکمیل؛ پذیرش Provider/VPS و ادغام main باز است (partial).

- W01: بازارهای حساب با صفحه‌بندی و جست‌وجوی بیش از ۱۱۰۰ بازار، ارزهای منتخب مستقل صرافی، migration افزایشی بدون تغییر جدول قدیمی FavoriteAsset.
- W02: Entry خالی، حجم صحیح زیر Entry، Spot بدون اهرم/Short، دو تب با حفظ وضعیت، درصد TP/SL و انتخابگر بازار و Drag & Drop.
- W03: Fix Loss خودکار از USDT آزاد تازه همان کیف Spot/Margin؛ مثال‌های 1000/5٪/1٪=200 و ریسک2٪=400، هشدارهای fee/lot/minimum، پیشنهاد صرفاً با انتخاب کاربر وارد مبلغ می‌شود.
- W04: پیش‌فرض‌های ذخیره‌شده بدون اعشار نمایشی، Trailing و Trailing SL، snapshot سهم TP و انتقال سهم هدف‌های حذف‌شده به آخرین هدف. منطق SL یک‌باره در TP1 با تست موتور موجود بررسی می‌شود؛ اجرای واقعی خروج موضوع S31 است.
- W05: ارسال اتمیک برنامه+snapshot+سفارش، quantity از Backend، request_key ثابت، مقابله با retry/همزمانی/قطع پاسخ و ادامه پس از step-up؛ صف پایدار در برابر قطع broker، نمایش TP/SL ذخیره‌شده و وضعیت در معاملات و نمودار.

قالب پایه styles.css تأییدشده بدون تغییر با blob 565980a9a4a5ba390f09fcc61c5a6ea9a6a82cdd حفظ شد. Source_plan روی سفارش nullable است تا سوابق قبلی حفظ شوند. رفع ناسازگاری schema از Stage29 r2 و پشتیبان‌گیری قبل از migration در نصب‌کننده حفظ شده‌اند.

دو regression قدیمی Margin simulator پس از تفکیک کیف‌های واقعی کشف و رفع شدند؛ فقط simulator/Paper بودجه مشترک دارد. آزمون مرورگر سرریز جدول جزئیات دسکتاپ را نیز کشف کرد و grid بدون تغییر سبک پایه محدود شد.

آزمون‌های Provider با داده مصنوعی و بدون شبکه صرافی هستند؛ پول واقعی استفاده نشده و فعال‌سازی سرور انجام نشده است. اجرای خودکار خروج واقعی و مدیریت خارجی در S31 تکمیل می‌شوند.


## شواهد اعتبارسنجی

- Source: 5f17849f720d476790c2fa6c2196ec8f4be8fff6
- CI: https://github.com/ostaddehdari/CryptoSniper/actions/runs/40357466172
- 369 آزمون PostgreSQL/Redis، 2 آزمون مسیر React، build، Ruff، security scan/pip-audit، Django check و migration drift موفق.
- 68 آزمون نصب‌کننده داخل مجموعه 369 آزمون موفق‌اند؛ migrationهای تاریخی تغییر نکرده‌اند.
- مرورگر: Entry پیش و پس از انتخاب بازار خالی، پیش‌فرض75 و TP2/2، Fix Loss200/400 بدون بازنویسی دستی، step-up و ادامه، قطع عمدی پاسخ201 سپس retry همان UUID فقط یک سفارش، quantity سرور، TP/SL ذخیره‌شده در معاملات/نمودار، DnD پایدار و logoutPOST.
- چهار مسیر اصلی در عرض‌های320/390/768/1440 بدون اسکرول افقی؛ خطای JavaScript صفر؛ artifact12666901314.
- Branch: stage30-final-trading؛ PR https://github.com/ostaddehdari/CryptoSniper/pull/4 روی Stage29؛ ادغام main ادعا نمی‌شود.
- مرحله بعد S31 است و در این درخواست آغاز نشده است.


## تحویل نصب

- Release: https://github.com/ostaddehdari/CryptoSniper/releases/tag/stage30-react-v0.30.0rc1-deploy-r1
- ZIP: CryptoSniper-Stage30-React-v0.30.0rc1-r1.zip
- ZIP SHA256: 311f990c14099c2ccda9a74c4b7a3b7ef0c38a8fd9e3d1bf705c1ab67a6ee5ad
- Installer SHA256: d887a65c2a1f1643f7b585fe253b60385d88842c03744c417b47ce89a7130a57
- Release دقیقاً از source آزموده‌شده بالا ساخته شد. scripts/deploy.sh همین دو فایل را با SHA256 کنترل و قبل از نصب --check اجرا می‌کند.
- این دستور نسخه هدف را نصب می‌کند؛ نصب واقعی Stage30 روی سرور اپراتور در این اجرا انجام نشده است. تنظیمات خصوصی و داده قبلی و backup قبل از migration از r2 حفظ شده‌اند.

دانلود واقعی هر دو asset از Release و کنترل SHA256 و اجرای scripts/deploy.sh --check موفق بود: CHECK_OK؛ هیچ نصبی انجام نشد.


پذیرش نصب Stage30: لاگ اپراتور Pasted text(20261026-171558).txt با دو migration OK، هفت صف سالم، PostgreSQL/Redis ready، Nginx200 و backupهای فعال، INSTALL_OK و DEPLOY_OK دریافت شد. پذیرش معامله واقعی صرافی و ادغام main همچنان جداگانه باز است.
