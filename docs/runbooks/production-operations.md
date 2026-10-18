# Runbook عملیات و استقرار CryptoSniper

این راهنما برای نسخه پایه بدون Telegram است. وجود فایل‌ها یا سبزشدن CI به‌تنهایی گواه استقرار VPS نیست؛ خروجی دستورات این سند باید روی همان هاست ثبت شود.

## پیش‌پرواز و تفکیک محیط

- Production با `DJANGO_SETTINGS_MODULE=config.settings.production` یا تنظیمات server مشتق از آن اجرا می‌شود؛ Staging با `config.settings.staging`.
- `CRYPTOSNIPER_ENVIRONMENT`، `CRYPTOSNIPER_RELEASE` و `CRYPTOSNIPER_SOURCE_REVISION` در process manager ثبت شوند. secret، URL دارای رمز و passphrase هرگز در لاگ یا Git قرار نگیرند.
- Node.js برای runtime لازم نیست. Web، هفت Worker و یک Beat باید processهای جدا و دائمی باشند. Listener تلگرام تا S21 نباید اجرا شود.

```bash
python backend/manage.py check --deploy
python backend/manage.py check_hosting --probe-outbound --probe-storage --json
python backend/manage.py check_deployment --json
python backend/manage.py check_release_candidate --probe-host --json
```

`check_hosting` نبود Worker، Beat، HTTPS، storage یا outbound HTTPS را fail-closed گزارش می‌کند. browser tab، cron کوتاه یا WSGI request جای Worker دائمی نیست.

## نصب و ارتقا

ابتدا `scripts/deploy.sh --check` و فقط پس از تطابق SHA نصب اجرا شود. installer باید تنظیمات خصوصی، دیتابیس، login و keyring را حفظ کند. تغییر Nginx فقط پس از backup و `nginx -t` اعمال می‌شود؛ در خطا rollback انجام می‌شود.

پس از ارتقا، `/health/live/`، `/health/ready/`، صفحه ورود، `/system/`، probe صف orders/reports و heartbeat هر هفت صف بررسی شوند. version/source در صفحه وضعیت باید با بسته نصب تطبیق داشته باشد.

## Worker، Beat و هشدار عملیاتی

- هر صف `signals`, `orders`, `market_data`, `trailing`, `alerts`, `reports`, `maintenance` heartbeat مستقل دارد.
- تنها یک Beat منطقی با lease Redis taskها را منتشر می‌کند. اجرای process دوم مجاز است اما بدون lease نباید task منتشر کند.
- snapshot مانیتور هر ۶۰ ثانیه depth صف، heartbeat، oldest pending، feed lag، dead-letter و account error را ثبت می‌کند.
- degraded بودن snapshot، stale شدن trailing feed یا dead-letter نیازمند توقف ورود جدید و reconciliation است؛ خروج حفاظتی خودکار متوقف نشود.

## Backup، offsite و restore drill

`CRYPTOSNIPER_BACKUP_PASSPHRASE` حداقل ۱۶ کاراکتر و خارج مخزن نگهداری شود. `HOSTING_BACKUP_OFFSITE_DIR` باید mount یا مسیر offsite مستقل باشد؛ خالی‌بودن آن warning واقعی است.

```bash
python backend/manage.py backup_deployment
python backend/manage.py backup_deployment --weekly
python backend/manage.py verify_backup /path/file.csbk --target cryptosniper_restore_YYYYMMDD
```

backup با `pg_dump` custom، AES-256-GCM و Scrypt ساخته می‌شود. نگهداری پیش‌فرض ۱۴ daily و ۸ weekly است. restore فقط به نام `cryptosniper_restore_*` مجاز است، migration و تعداد audit row را می‌سنجد و DB آزمون را حذف می‌کند. `HOSTING_RESTORE_ADMIN_URL` باید secret اتصال ادمین محدودِ مخصوص ساخت/حذف DB آزمون باشد؛ DB بازیابی‌شده با مالکیت نقش برنامه ساخته می‌شود. rollback برنامه نباید audit دیتابیس را حذف یا migration برگشت‌ناپذیر را خودکار معکوس کند.

## Incident و rollback

برای نشت credential از [راهنمای رخداد امنیتی](security-incident.md) استفاده شود. برای خرابی نسخه، ورود جدید را pause، backup جدید بگیرید، app/unit/Nginx را به backup installer برگردانید و سپس readiness و reconciliation را اجرا کنید. نتیجه نامعلوم سفارش هرگز موفق فرض نشود.

## محدودیت‌های اعلامی

- Binance write واقعی خاموش و sandbox/live بررسی‌نشده است.
- Margin Long/Short فقط دفتر Simulator Paper است.
- Provider واقعی 2FA انتخاب نشده است.
- Telegram، parser کانال، Telethon و AI/channel analytics فقط در S21 پیاده‌سازی می‌شوند.
