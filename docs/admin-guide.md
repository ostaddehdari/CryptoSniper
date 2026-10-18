# راهنمای ادمین نسخه پایه 0.20

Production به Python 3.12، PostgreSQL 16، Redis 7، HTTPS، فضای backup و هفت Worker دائمی برای `orders,reports,signals,market_data,trailing,alerts,maintenance` به‌علاوه دقیقاً یک Beat نیاز دارد. Node.js در runtime لازم نیست.

## پیش از انتشار

1. `check_hosting --strict`، `check_deployment --migrations` و `check_release_candidate` را در محیط مقصد اجرا کنید.
2. `CRYPTOSNIPER_RELEASE`، `CRYPTOSNIPER_SOURCE_REVISION` و `CRYPTOSNIPER_ENVIRONMENT=production` را صریح تنظیم کنید.
3. migration و collectstatic را پیش از restart Web انجام دهید؛ shutdown Workerها باید graceful باشد.
4. `/health/ready/`، `/api/v1/deployment/readiness/`، `/api/v1/operations/host-capabilities/` و `/api/v1/acceptance/` را با نشست ادمین بررسی کنید.

## Backup و بازیابی

`backup_deployment` از `pg_dump`، Scrypt و AES-256-GCM استفاده می‌کند؛ passphrase باید فقط در secret manager یا فایل root-only خارج Git باشد. مقصد offsite مستقل را تنظیم کنید. `verify_backup` فقط دیتابیس جدا با پیشوند `cryptosniper_restore_` را می‌پذیرد و production target را رد می‌کند. برای ساخت/حذف همین DB جدا، `HOSTING_RESTORE_ADMIN_URL` باید به اتصال ادمین محدودِ مخصوص drill اشاره کند؛ DB بازیابی‌شده با مالکیت نقش برنامه ساخته می‌شود. نتیجه backup بدون restore drill مدرک بازیابی نیست.

## مانیتور و رخداد

freshness هر هفت Worker، Beat، عمق صف، قدیمی‌ترین outbox، feed lag، dead-letter و خطای حساب را پایش کنید. در رخداد، ورود جدید را pause کنید، وضعیت receipt/provider را reconcile کنید و نتیجه نامعلوم را موفق فرض نکنید. rollback باید با سازگاری migration و حفظ audit انجام شود.

اجرای واقعی Binance عمداً غیرفعال است. فعال‌کردن آن، افزودن Telethon یا ذخیره secret در مخزن خارج از دامنه این انتشار است.
