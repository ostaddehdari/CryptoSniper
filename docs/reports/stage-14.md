# استیج ۱۴ — مدیریت معاملات و جزئیات | 0.14.0rc1

هر پنج ورک برای Paper Spot Long شبیه‌ساز پیاده شده‌اند. اجرای واقعی Binance، Margin/Short و مدیریت معاملات External غیرفعال است؛ پذیرش این قابلیت‌ها و VPS همچنان باز و وضعیت رسمی partial است.

| ورک | نتیجه |
|---|---|
| S14-W01 | معاملات فعال و History، نماد/حساب/صرافی/market/جهت/entry/current/quantity/leverage/TP/SL/trailing/P&L/duration/source؛ فیلتر و pagination بیست‌ردیفی و API مالکیتی |
| S14-W02 | متن اصلی و مقادیر ساختارمند سیگنال، Plan و snapshot تثبیت‌شده، Orders/receipts/Fills/fees، timeline صفحه‌بندی‌شده با whitelist داده |
| S14-W03 | لغو ورود ارسال‌نشده، بستن باقی‌مانده با تأیید و audit، SL/trailing با version، توقف ورود جدید با تأیید در مرکز عملیات |
| S14-W04 | pending، نتیجه نامعلوم، انتظار قیمت و نیاز به تطبیق؛ polling وضعیت هر ۵ ثانیه و توضیح قطعی شبکه؛ مسیر مرکز عملیات و نتیجهٔ recovery |
| S14-W05 | UI→درخواست پایدار→orders Worker→Fill؛ PostgreSQL concurrency برای close در برابر stop/TP/close، تکرار درخواست و دسترسی کاربر دیگر |

## دوام و هم‌زمانی

POST بستن، TradeAction دارای UUID و revision را در DB ثبت می‌کند. مرورگر قیمت اجرا تعیین نمی‌کند. Beat scanner مستقل، درخواست‌های pending/waiting_feed را به orders می‌فرستد؛ توقف ورود جدید خروج محافظتی/بستن را متوقف نمی‌کند. کلید تکراری همان نتیجه را می‌دهد؛ کلید متفاوت در زمان pending به همان درخواست جاری می‌پیوندد. نسخه متفاوت برای کلید یکسان رد می‌شود.

Worker قیمت تازه را از adapter شبیه‌ساز می‌گیرد یا در حالت سناریوی دستی از آخرین Tick معتبر همان معامله استفاده می‌کند؛ cache نمایشی قیمت اجرا نیست. نبود قیمت، waiting_feed می‌سازد و پس از ۱۵ ثانیه دوباره بررسی می‌شود. Timeout هرگز شکست قطعی یا Fill فرضی نمی‌شود.

قفل PostgreSQL روی Trade با موتور SL/TP مشترک است. موجودی باقی‌مانده در زمان اجرا خوانده می‌شود. Fill، Position، بسته‌شدن، پایان حفاظت، آزادشدن رزرو، خاموشی هشدار و نتیجهٔ درخواست در یک تراکنش ثبت می‌شوند. crash پیش از commit همه را rollback می‌کند؛ پس از commit تحویل تکراری نتیجهٔ ثبت‌شده را برمی‌گرداند. اگر SL/TP قبلاً بسته باشد، نتیجه already_closed است.

ورود ناقص، درحال ارسال، نامعلوم یا لغو خروج نامشخص نیازمند تطبیق است و بستن جدید را مسدود می‌کند؛ در این نسخه remainder ورود جزئی خودکار لغو نمی‌شود. این محدودیت مانع بازشدن Position با Fill دیررس پس از close است. لغو ورود فقط پیش از claim/ارسال مجاز و replay لغو بدون اثر مضاعف است. SL/trailing همچنان قیود monotonic/version و قوانین محافظتی پیشین را دارند.

## داده و پذیرش

پاسخ خام provider/credential/snapshot دلخواه به مرورگر ریخته نمی‌شود؛ شناسه رسید، مقادیر Fill و فیلدهای محدود event و snapshot نمایش داده می‌شوند. External تنها مشاهده است و هزینه ورود یا Position مدیریت‌شده برای آن حدس زده نمی‌شود. GET هیچ عملیات مالی انجام نمی‌دهد؛ POSTها مالکیتی و CSRF-protected هستند.

نتیجه نهایی CI و Release در جمع‌بندی ثبت می‌شود. پذیرش واقعی VPS نسخه 0.14، حساب Binance و حجم بزرگ هنوز انجام نشده است. Telethon/AI طبق برنامه فقط در S21 است؛ توسعه S15 از این درخواست نتیجه نمی‌شود.

## نتیجهٔ بررسی نهایی

- [CI موفق منبع دقیق](https://github.com/ostaddehdari/CryptoSniper/actions/runs/39045862763)، commit `83e3db394728c0e8b379165cf2ce53873106b561`، artifact `12104864902`: **۱۳۷ تست موفق**؛ lint/format، Django check، migration drift، migration واقعی، PostgreSQL/Redis، هفت Worker و Beat و Chromium.
- بستن با تأیید UI تا Fill در orders Worker، رقابت close/SL/TP، replay و مالکیت پاس شد. داشبورد دارای داده و History روی موبایل، عرض‌های ۳۲۰/۳۹۰/۷۶۸، دسکتاپ، offline/reconnect و نبود خطای JS/overflow پاس شد. هشدار و ثبت مستقل پس از بستن مرورگر نیز همچنان پاس است.
- بودجهٔ داشبورد در workload کوچک آزمون: **۱۶ query و ۲۵٫۷۶ میلی‌ثانیه** build سمت سرور؛ تضمین latency یا ظرفیت VPS نیست.
- نصب‌کنندهٔ Stage14 دوازده آزمون regression مشترک Stage12/14 برای headerهای قبلی، unmanaged/تغییر هم‌زمان، نصب مسیر و rollback را پاس کرد. فایل‌های واقعی Nginx سرور در این آزمون‌ها تغییر نکردند.
- Release تجمیعی منتشرشده: [stage14-v0.14.0rc1-deploy](https://github.com/ostaddehdari/CryptoSniper/releases/tag/stage14-v0.14.0rc1-deploy). SHA256SUMS و runlog همراه بسته منتشر می‌شوند؛ workflow انتشار فقط commit با CI موفق را بسته‌بندی و `--check` را پیش از انتشار اجرا می‌کند.

## بستهٔ منتشرشده و کنترل مستقل

[ساخت Release و CHECK_OK](https://github.com/ostaddehdari/CryptoSniper/actions/runs/39046433819) از commit `aa22b995b70d5394f296ba387837ed4c4ee6427b` با [CI موفق همان منبع](https://github.com/ostaddehdari/CryptoSniper/actions/runs/39046206076). ZIP، نصب‌کننده، runlog و SHA256SUMS منتشر شدند. bytes هر چهار فایل از artifact `12106335977` دوباره دانلود و با digest دارایی‌های GitHub Release تطبیق داده شدند؛ اجرای مستقل `--check` هم CHECK_OK داد و هیچ سرویسی نصب نشد.

- ZIP SHA256: `4e16302de319c8277f96155e5f671e84df4acecec878db6d31963c9aeef96fd4`
- Installer SHA256: `6136648196c48c714e25900965758c2b1a5ff97d054332e4fe878048c257254e`
- `scripts/deploy.sh` همین tag و هر دو SHA را pin می‌کند. لاگ اپراتور در 2026-10-17 نصب موفق Stage14، حفظ داده/تنظیمات/keyring/login، سلامت ده سرویس و HTTP 200 مسیرهای readiness/login روی Nginx محلی را تأیید کرد؛ پذیرش مرورگر عمومی همچنان باز است.
