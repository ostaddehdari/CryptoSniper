# راه‌اندازی CryptoSniper تا استیج ۲

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
uv run --env-file .env celery --workdir backend -A config worker -Q orders,maintenance --concurrency=1 -n orders@%h
uv run --env-file .env celery --workdir backend -A config worker -Q reports --concurrency=1 -n reports@%h
uv run --env-file .env celery --workdir backend -A config beat --schedule .runtime/celerybeat-schedule
```

قبل اجرای Beat پوشه `.runtime` را ایجاد کنید. فقط یک instance از Beat اجرا شود. Worker سفارش و Worker گزارش جدا هستند؛ وظیفه سنگین گزارش نباید پردازش سفارش را متوقف کند. در این استیج صف سفارش فقط probe زیرساختی اجرا می‌کند و هنوز موتور معامله وجود ندارد.

صفحه ورود: `http://127.0.0.1:8000/auth/login/`؛ پس از ورود صفحه نمای کلی و `/system/` برای بررسی سرویس‌ها در دسترس است. پروفایل، نشست‌های فعال، بازیابی رمز، پیش‌فرض‌های معامله و گزارش امنیتی از منوی تنظیمات در دسترس‌اند.

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

برای ASGI، `uvicorn config.asgi:application --app-dir backend` قابل استفاده است. TLS باید روی هاست یا reverse proxy تنظیم شود. فقط پشت proxy قابل اعتماد که هدر ورودی کاربر را حذف می‌کند `DJANGO_PROXY_SSL_HEADER=true` شود. مشخصات هاست و استقرار واقعی در S19 بررسی خواهند شد؛ این سند گواه استقرار روی سرور کاربر نیست.

## مرز تحویل

تا پایان استیج ۲ زیرساخت، حساب و امنیت پایه، تنظیمات، رابط و health/Worker/CI آماده‌اند. اتصال صرافی، parser سیگنال و معاملات هنوز در این نسخه فعال نیستند. Telethon و AI صرفاً در S21 اضافه می‌شوند.
