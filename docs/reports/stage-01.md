# گزارش تحویل استیج ۱ — نسخه ۰٫۱٫۰

واحد تحویل: تمام پنج ورک S01. مخزن `ostaddehdari/CryptoSniper`، شاخه `main`؛ تاریخ ۶ اکتبر ۲۰۲۶.

## نتیجه ورک‌ها

| ورک | نتیجه |
|---|---|
| S01-W01 | Python/Django، ساختار modular، محیط‌های مستقل، secret اجباری، env نمونه، gitignore و قفل وابستگی‌ها ساخته شد. |
| S01-W02 | PostgreSQL و Redis، مدل کاربر از اولین migration، UTC، health/live و health/ready و پاسخ 503 به خرابی ساخته و بررسی شد. |
| S01-W03 | Celery/Beat، سه صف orders/reports/maintenance، پردازش مستقل، heartbeat، probe یکتا و correlation ID با لاگ JSON ساخته شد. |
| S01-W04 | ورود/خروج واقعی، صفحات محافظت‌شده، پوسته روشن RTL موبایل/دسکتاپ، منوی موبایل، پروفایل بازشونده، Dark اختیاری و پایش واقعی سرویس‌ها آماده شد. |
| S01-W05 | GitHub Actions، نصب از قفل، checks/migrations، pytest و smoke واقعی PostgreSQL/Redis/Worker/Beat/مرورگر، شواهد آزمون و راهنمای اجرا آماده شد. |

## بررسی‌های انجام‌شده

اجرای مرجع روی GitHub runner با Ubuntu 24.04، Python 3.12.14، PostgreSQL 16.15 و Redis 7.4.11 انجام شد. بسته‌های اصلی نصب‌شده: Django 5.2.18، Celery 5.6.3 و psycopg 3.3.6؛ تمام بسته‌ها در `uv.lock` ثبت‌اند.

| بررسی | نتیجه |
|---|---|
| نصب محیط تازه `uv sync --frozen` | موفق |
| `ruff check` و `ruff format --check` | موفق |
| Django check، تشخیص migration جاافتاده و migrate روی PostgreSQL | موفق |
| ۱۶ تست pytest | همه موفق |
| اتصال واقعی PostgreSQL و Redis cache/broker/results | موفق |
| task روی orders و reports، receipt دیتابیس و PID متفاوت از درخواست‌کننده | موفق |
| ارسال heartbeat توسط Beat به maintenance Worker | موفق |
| ورود واقعی و رابط دسکتاپ؛ HTMX و Alpine بدون خطای JS | موفق |
| عرض‌های موبایل/تبلت ۳۲۰، ۳۹۰ و ۷۶۸ بدون overflow افقی | موفق |
| بستن مرورگر و ادامه Worker تا ثبت نتیجه در PostgreSQL | موفق |

تست‌ها حفاظت CSRF، خروج فقط با POST، جلوگیری از redirect بیرونی، مالکیت receipt، رد secret خالی/کوتاه، رد SQLite و host wildcard در Production، UTC و redaction را پوشش می‌دهند. خطای DB/Redis در تست واحد با تزریق خطا بررسی شد؛ آزمایش قطع گسترده سرویس و بازیابی موتور معامله در استیج ۱۱ خواهد بود.

نمونه دستورهای اجرا و کاربرد processهای مستقل در [راهنمای نصب](../setup.md) آمده است. CI مرورگر Chromium را نیز نصب و چهار screenshot و JUnit XML را تولید می‌کند.

## شواهد و کامیت‌ها

اجرای موفق کد پایه: [GitHub Actions شماره 37489798582](https://github.com/ostaddehdari/CryptoSniper/actions/runs/37489798582)، commit `172f7dc4f13d6b7019117cd7fc82aaa1978c826b`. در این اجرا همه تست‌ها و smoke موفق بودند؛ upload شواهد به‌دلیل hidden بودن پوشه اجرا نشد و سپس تنظیم آن اصلاح شد.

اجرای اصلاح CI و شواهد: [GitHub Actions شماره 37490252174](https://github.com/ostaddehdari/CryptoSniper/actions/runs/37490252174)، commit `75523d1214b9c7de7fcdd9c4b652a08f5cc0b929`. این اجرا نیز با نتیجه `success` پایان یافت: ۱۶ تست و تمام smoke checks موفق شدند. بسته [stage-01-evidence](https://github.com/ostaddehdari/CryptoSniper/actions/runs/37490252174/artifacts/11424494177) شامل JUnit XML و چهار screenshot آپلود شد؛ نگهداری آن در Actions هفت روز است. تصاویر دسکتاپ و موبایل نیز پس از دریافت به‌صورت بصری بررسی شدند. masking راز موقت CI در لاگ اجرای اصلاح‌شده تأیید شد.

| شناسه | کامیت GitHub |
|---|---|
| S01-W01 | `036b597feb259ad8116cb680c3722a0c2e164e5a` |
| S01-W02 | `8d5febf38cd1785d54b07fbbe4d82bfd9623411c` |
| S01-W03 | `a116391cdb227c58351226d634e1c311f2c63cbd` |
| S01-W04 | `6acaec21cadfa295460f2b1c95bf6261db4cd414` |
| S01-W05 | `6ab95a135caf139d5c37ef8350b00663727bf9ee` |
| اصلاح آزمون دیتابیس/یکتایی Worker | `172f7dc4f13d6b7019117cd7fc82aaa1978c826b` |
| اصلاح شواهد و masking CI | `75523d1214b9c7de7fcdd9c4b652a08f5cc0b929` |

SHA کامیت جمع‌بندی، پس از ثبت در پاسخ تحویل گزارش می‌شود و داخل محتوای همان کامیت نوشته نمی‌شود. کامیت جمع‌بندی فقط مستندات و وضعیت برنامه را تغییر می‌دهد؛ با `[skip ci]` از تکرار بی‌دلیل همان آزمون‌ها جلوگیری می‌شود. آخرین کد و workflow آزموده‌شده همان commit `75523d1214b9c7de7fcdd9c4b652a08f5cc0b929` است.

## محدودیت واقعی تحویل

- آزمایش یکپارچه و مرورگر روی runner واقعی GitHub انجام شد؛ محیط Scratch محدودیت اجرای PostgreSQL با کاربر غیرریشه و دریافت binary مرورگر داشت. نتیجه CI جای آزمایش روی هاست کاربر معرفی نشده است.
- هاست مشخص یا نصب‌شده برای این پروژه وجود ندارد. استقرار واقعی در استیج ۱۹ انجام می‌شود.
- در این استیج اتصال صرافی، parser سیگنال، معامله، TP/SL و Trailing پیاده‌سازی نشده‌اند؛ کارت‌های داشبورد عدد سود یا موجودی ساختگی نمایش نمی‌دهند.
- ورود پایه با نام کاربری است. پروفایل، ورود ایمیلی، تنظیمات حساب، بازیابی رمز و امنیت تکمیلی در استیج ۲ ساخته می‌شوند.
- Telethon، خواندن کانال و تحلیل قالبی یا هوش مصنوعی مطابق دستور کاربر فقط S21 هستند.

استیج بعد: S02 — حساب کاربری، تنظیمات و امنیت پایه. اجرای آن نیازمند دستور بعدی کاربر است.
