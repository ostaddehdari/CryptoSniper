# راهنمای ادمین نسخه 0.21

Production به Python 3.12، PostgreSQL 16، Redis 7، HTTPS، فضای backup، هفت Worker دائمی برای `orders,reports,signals,market_data,trailing,alerts,maintenance`، یک Beat و سرویس مستقل `cryptosniper-telegram` نیاز دارد. Node.js در runtime لازم نیست.

## پیش از انتشار

1. `check_hosting --strict`، `check_deployment --migrations` و `check_release_candidate` را در محیط مقصد اجرا کنید.
2. `CRYPTOSNIPER_RELEASE`، `CRYPTOSNIPER_SOURCE_REVISION` و `CRYPTOSNIPER_ENVIRONMENT=production` را صریح تنظیم کنید.
3. migration و collectstatic را پیش از restart Web انجام دهید؛ shutdown Workerها باید graceful باشد.
4. `/health/ready/`، `/api/v1/deployment/readiness/`، `/api/v1/operations/host-capabilities/` و `/api/v1/acceptance/` را با نشست ادمین بررسی کنید.

## Backup و بازیابی

`backup_deployment` از `pg_dump`، Scrypt و AES-256-GCM استفاده می‌کند؛ passphrase باید فقط در secret manager یا فایل root-only خارج Git باشد. مقصد offsite مستقل را تنظیم کنید. `verify_backup` فقط دیتابیس جدا با پیشوند `cryptosniper_restore_` را می‌پذیرد و production target را رد می‌کند. برای ساخت/حذف همین DB جدا، `HOSTING_RESTORE_ADMIN_URL` باید به اتصال ادمین محدودِ مخصوص drill اشاره کند؛ DB بازیابی‌شده با مالکیت نقش برنامه ساخته می‌شود. نتیجه backup بدون restore drill مدرک بازیابی نیست.

## مانیتور و رخداد

freshness هر هفت Worker، Beat، عمق صف، قدیمی‌ترین outbox، feed lag، dead-letter و خطای حساب را پایش کنید. در رخداد، ورود جدید را pause کنید، وضعیت receipt/provider را reconcile کنید و نتیجه نامعلوم را موفق فرض نکنید. rollback باید با سازگاری migration و حفظ audit انجام شود.

## Telegram، AI و صرافی‌های Spot

ورود Telegram از UI محافظت‌شده با step-up انجام می‌شود؛ session/API hash رمزنگاری‌شده‌اند. سلامت `cryptosniper-telegram` و heartbeat آن را پایش کنید. AI اختیاری است و بدون endpoint/model/key پیکربندی‌شده صریحاً blocked می‌ماند؛ کلید را فقط در secret store محیط قرار دهید.

پنج provider `nobitex,lbank,weex,ourbit,bitunix` حاضرند. برای هر حساب کلید Read+Spot بدون Withdrawal و IP allowlist بسازید. ابتدا اتصال و sync بدون پول را بررسی کنید. `LIVE_TRADING_ENABLED=false` پیش‌فرض است؛ تنها پس از بررسی حقوقی، permission واقعی، limits/precision و سفارش کم‌ریسک کنترل‌شده آن را در `.env` به `true` تغییر و سرویس‌های Web/Orders را restart کنید. این متغیر Full-Auto Telegram را Live نمی‌کند؛ آن مسیر همیشه Paper است.

Futures/Perpetual و Margin واقعی غیرفعال‌اند. هر `uncertain` باید با client/exchange order ID در provider reconcile شود و هرگز خودکار retry نشود. Nobitex و هر provider دیگر فقط پس از بررسی تحریم، حوزه قضایی و eligibility کاربر استفاده شود.
