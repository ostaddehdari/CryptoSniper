# پذیرش Recovery، Backup و امنیت — Stage20

ماتریس خودکار سناریوهای crash قبل و بعد submit، timeout، retry محدود، task تکراری، fence قدیمی، cancel/fill race، قطع Redis، feed قدیمی، browser close و reconciliation را اجرا می‌کند. receipt شبیه‌ساز مستقل از executor پایدار است؛ recovery ابتدا lookup می‌کند و نتیجهٔ نامعلوم را موفق فرض نمی‌کند. یک `client_order_id` فقط یک provider receipt و یک Fill ورودی می‌سازد.

مالکیت object در UI/API، CSRF، escaping، SSRF، rate/body limit، session revocation، step-up، credential rotation/revocation و redaction دوباره بررسی می‌شوند. gate انتشار private key، AWS key، فعال‌شدن Live، `TRADING_MODE=live` و passphrase پشتیبان commit‌شده را blocker می‌داند. dependency audit جداگانه در CI اجرا می‌شود و critical/high باز باید صفر باشد.

backup دیتابیس با pg_dump، AES-256-GCM و Scrypt ساخته می‌شود. restore drill فقط روی دیتابیس جدا با پیشوند `cryptosniper_restore_` مجاز است؛ production target رد می‌شود و وجود migration و audit row بررسی می‌گردد. مقصد offsite تا زمانی که اپراتور مسیر مستقل تنظیم نکرده باشد «پیکربندی نشده» گزارش می‌شود.

این شواهد برای Simulator Paper و CI disposable معتبر است. restart واقعی VPS، restore روی PostgreSQL همان سرور و پذیرش عمومی HTTPS فقط با لاگ اپراتور نهایی می‌شوند.
