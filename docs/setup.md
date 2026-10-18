# راه‌اندازی CryptoSniper — نسخه تجمعی استیج ۲۰

نیازها: Python 3.12 یا نسخه سازگار قفل وابستگی‌ها، PostgreSQL 16، Redis 7، uv و پردازش‌های مستقل Web، Worker و Beat. Node.js برای اجرا لازم نیست. وابستگی‌های دقیق در `uv.lock` ثبت شده‌اند. Django 5.2 LTS انتخاب شده است؛ نسخه patch نصب‌شده 5.2.18 است.

## محیط توسعه

از ریشه مخزن:

```bash
uv sync --frozen
uv run python scripts/bootstrap.py
docker compose up -d postgres redis
uv run python backend/manage.py migrate
uv run python backend/manage.py collectstatic --noinput
uv run python backend/manage.py createsuperuser
uv run python backend/manage.py runserver 127.0.0.1:8000
```

Docker فقط گزینه راحت توسعه است. روی هاست یا سیستم دارای PostgreSQL و Redis، مقادیر URL در `.env` را با سرویس‌های واقعی هماهنگ کنید و دستور compose را حذف کنید. اسکریپت bootstrap راز تصادفی و رمز PostgreSQL تولید می‌کند، آنها را چاپ نمی‌کند و فایل موجود را بازنویسی نمی‌کند. هیچ حساب با رمز پیش‌فرض داخل پروژه وجود ندارد. PostgreSQL توسعه برای اجرای pytest باید اجازه ساخت test database داشته باشد.

در ترمینال‌های جدا، پردازش‌ها را اجرا کنید:

```bash
for queue in orders reports signals market_data trailing alerts maintenance; do
  uv run --env-file .env celery --workdir backend -A config worker -Q "$queue" --concurrency=1 -n "$queue@%h" &
done
uv run --env-file .env celery --workdir backend -A config beat --schedule .runtime/celerybeat-schedule
```

قبل اجرای Beat پوشه `.runtime` را ایجاد کنید. فقط یک instance از Beat اجرا شود. Worker سفارش و Worker گزارش جدا هستند؛ وظیفه سنگین گزارش نباید پردازش سفارش را متوقف کند. صف سفارش ورود و بستن Paper را مستقل از مرورگر اجرا می‌کند؛ صف trailing خروج‌های Paper و صف maintenance بازیابی و scanner را انجام می‌دهند. اجرای واقعی سفارش غیرفعال است.

صفحه ورود: `http://127.0.0.1:8000/auth/login/`؛ پس از ورود صفحه نمای کلی و `/system/` برای بررسی سرویس‌ها در دسترس است. پروفایل، نشست‌های فعال، بازیابی رمز، پیش‌فرض‌های معامله و گزارش امنیتی از منوی تنظیمات در دسترس‌اند.

مرکز صرافی در `/exchanges/` قرار دارد. برای مشاهده بدون کلید، «شبیه‌ساز CryptoSniper» را اضافه کنید. کلیدهای واقعی با AES-256-GCM رمزنگاری می‌شوند و متغیر `EXCHANGE_CREDENTIAL_KEYS` باید به‌صورت `version:urlsafe-base64` تنظیم شود. `scripts/bootstrap.py` برای محیط توسعه یک کلید خصوصی تصادفی می‌سازد. برای rotation، کلید نسخه جدید را به انتهای keyring اضافه کنید؛ حذف کلید قدیمی قبل از re-encrypt رکوردها ممنوع است.

## بررسی خودکار

```bash
uv run ruff check backend tests scripts
uv run ruff format --check backend tests scripts
uv run python backend/manage.py check
uv run python backend/manage.py makemigrations --check --dry-run
uv run pytest
uv run playwright install --with-deps chromium
uv run python scripts/smoke.py
```

smoke فقط روی دیتابیس محلی توسعه و قابل حذف اجرا شود. Workerهای سه صف، Beat و Web را در processهای مستقل می‌سازد و در پایان می‌بندد. نتیجه probe صف سفارش و گزارش، heartbeat زمان‌بندی، ورود واقعی، نمایش HTMX، منوی Alpine و نبود overflow در عرض‌های ۳۲۰/۳۹۰/۷۶۸ را بررسی می‌کند. پس از بستن مرورگر باید receipt Worker در PostgreSQL موجود باشد. screenshotهای بررسی در `.runtime/screenshots/` ایجاد می‌شوند.

`/health/live/` فقط زنده‌بودن Web را بررسی می‌کند. `/health/ready/` اتصال PostgreSQL و Redis cache/broker/results را بررسی می‌کند و در نبود وابستگی 503 می‌دهد. وضعیت Worker/Beat با heartbeat واقعی و اجرای probe جدا سنجیده می‌شود؛ اتصال broker به‌تنهایی به‌معنی وجود Worker نیست.

## تنظیمات Production و Staging

در process manager هاست `DJANGO_SETTINGS_MODULE=config.settings.production` یا `config.settings.staging` را صریحاً تنظیم کنید. secret تصادفی حداقل ۵۰ کاراکتر، Allowed Hosts دقیق و URLهای واقعی DB/Redis لازم‌اند. Production با host wildcard یا secret خالی اجرا نمی‌شود. SQLite پذیرفته نیست. Cookies در Production Secure و HTTPOnly هستند و CSRF فعال است.

```bash
uv sync --frozen --no-dev
uv run --no-dev python backend/manage.py migrate
uv run --no-dev python backend/manage.py collectstatic --noinput
uv run --no-dev gunicorn --chdir backend config.wsgi:application --bind 127.0.0.1:8000
```

برای ASGI، `uvicorn config.asgi:application --app-dir backend` قابل استفاده است. TLS باید روی هاست یا reverse proxy تنظیم شود. فقط پشت proxy قابل اعتماد که هدر ورودی کاربر را حذف می‌کند `DJANGO_PROXY_SSL_HEADER=true` شود. ممیزی S19 با `check_hosting --strict` و readiness استقرار با `check_deployment --migrations` انجام می‌شود؛ این سند یا پاس‌شدن CI به‌تنهایی گواه استقرار روی سرور کاربر نیست.

## مرز تحویل

نسخه 0.3.0rc1 اتصال امن، شبیه‌ساز و همگام‌سازی صرافی را اضافه می‌کند. Adapter خواندنی Binance پیاده‌سازی شده، اما تا آزمایش با کلید مجاز کاربر «اتصال واقعی تأییدشده» محسوب نمی‌شود. ارسال سفارش واقعی همچنان مسدود است؛ parser سیگنال و موتور معامله هنوز فعال نیستند. Telethon و AI صرفاً در S21 اضافه می‌شوند.

## Dashboard و مدیریت معاملات 0.14

پس از ورود، داشبورد موجودی و نتایج واقعی همان کاربر را به تفکیک حساب و ارز نشان می‌دهد. برای نرخ/موجودی قدیمی یا نامعلوم، ابتدا اتصال و همگام‌سازی حساب را بررسی کنید؛ عدد برآوردی جای موجودی قابل معامله نیست.

در «معاملات و تاریخچه»، فیلتر حساب/نماد/منبع/وضعیت و pagination موجود است. در جزئیات، متن اصلی/طرح/Fills و رویدادها را بررسی کنید. «بستن باقی‌مانده» نیاز به تأیید صریح دارد و تنها پس از نتیجهٔ Worker و Fill، بسته‌شدن قطعی است. انتظار قیمت با شکست سفارش یکی نیست؛ در نتیجهٔ ورود نامعلوم/ناقص ابتدا مرکز عملیات و تطبیق را اجرا کنید. تغییر Stop/trailing و توقف ورود جدید نیز تأیید می‌خواهند. توقف ورود جدید خروج حفاظتی را متوقف نمی‌کند.

ارتقای Ubuntu 24.04 از `scripts/deploy.sh` همان release رسمی و checksum ثابت را می‌گیرد. ابتدا `--check` و سپس نصب را اجرا کنید. نصب‌کننده Stage14 داده، رمز ورود و keyring قبلی را حفظ و headerهای دقیق مدیریت‌شده Stage01–14 را شناسایی می‌کند. فایل Nginx ناشناس را بازنویسی نمی‌کند؛ backup و rollback ادامه دارند. نصب موفق Stage14 با لاگ اپراتور در 2026-10-17 تأیید شده است؛ پذیرش مرورگر عمومی همچنان باز است.

## Reports و PWA نسخه 0.16

Stage15 محاسبات Decimal و گزارش‌های aggregate/CSV/SVG را اضافه می‌کند و Stage16 رابط موبایل/دسکتاپ و PWA را تکمیل می‌کند. Service Worker فقط static assetهای عمومی را cache می‌کند؛ پاسخ خصوصی، API، navigation و عملیات POST هرگز برای اجرای آفلاین ذخیره نمی‌شوند. نصب‌کننده Stage16 نصب مدیریت‌شده Stage14 و headerهای دقیق Stage01–16 را می‌پذیرد، اما snippet ناشناس یا تغییر هم‌زمان Nginx را بدون بازنویسی رد می‌کند. deploy این نسخه ZIP و installer تأییدشده را از commit ثابت `104038e39090d2ba911ea1c7281ff39709270016` می‌گیرد؛ بنابراین تغییر بعدی شاخهٔ main bytes نصب را عوض نمی‌کند.

لاگ اپراتور نصب موفق Stage14 را تأیید کرده است. برای Stage16 ابتدا `scripts/deploy.sh --check` و سپس نصب عادی را اجرا کنید؛ نتیجهٔ نصب 0.16 تا ارائهٔ لاگ جدید تأییدشده محسوب نمی‌شود.

## عملیات و تحویل نسخه 0.20

نسخه 0.20 هفت Worker دائمی، دقیقاً یک Beat، monitor صف/feed/exchange، هویت release/source/environment، backup رمزنگاری‌شده و restore فقط روی دیتابیس جدا را بررسی می‌کند. جزئیات روزمره در [راهنمای ادمین](admin-guide.md)، مسیر محصول در [راهنمای کاربر](user-guide.md) و مرز شواهد در [چک‌لیست پذیرش](acceptance/stage20-checklist.md) آمده است.

پس از نصب، readiness عمومی و login باید 200 باشند و APIهای خصوصی deployment، host capabilities و acceptance با نشست معتبر بررسی شوند. نتیجهٔ CI جای restart، restore و مرورگر عمومی VPS را نمی‌گیرد. `CRYPTOSNIPER_BACKUP_PASSPHRASE` را در Git یا log قرار ندهید و مقصد offsite را روی storage مستقل تعریف کنید.

Release رسمی `stage20-v0.20.0rc1-deploy` از commit ثابت `89bb6653a5b24b062373b5ee0ed4539c18c6c1c8` ساخته شده است. `scripts/deploy.sh` فقط ZIP و installer دارای SHA ثابت همین Release را اجرا می‌کند. نصب‌کننده پس از migration یک backup رمزنگاری‌شده اولیه می‌سازد و timerهای روزانه/هفتگی را فعال می‌کند؛ offsite و `HOSTING_RESTORE_ADMIN_URL` همچنان باید متناسب با هاست و خارج Git تنظیم شوند.

## استیج 0.21: Telegram و پنج صرافی Spot

نصب‌کننده 0.21 سرویس `cryptosniper-telegram` را کنار هفت Worker و Beat می‌سازد و `LIVE_TRADING_ENABLED=false` را برای نصب تازه ثبت می‌کند. ارتقا `.env`، keyring، دیتابیس و ورود موجود را حفظ می‌کند. پس از نصب، تنظیمات Telegram و اتصال Nobitex/LBank/WEEX/Ourbit/Bitunix از UI انجام می‌شود؛ secret را در shell history یا مستندات وارد نکنید.

Release رسمی `stage21-v0.21.0rc1-deploy` از commit ثابت `e315e1983bb916ed8867a721b583e9b2c55eb93a` پس از ۲۴۵ آزمون exact-source ساخته شد. `scripts/deploy.sh` به ZIP با SHA-256 برابر `8a44ba2e8e1d61806a122d93bf92f6e3eccc85fa291fc3f51c327469141e0d41` و installer با SHA-256 برابر `5d9a4f5e9cf1783ce7ad57a58c39a63b632c7d22611ba6833ccff6757a3cb41c` pin است. این شواهد جای نصب و پذیرش واقعی VPS/provider را نمی‌گیرد.
