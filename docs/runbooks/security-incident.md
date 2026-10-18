# Runbook رخداد امنیتی و خرابی اتصال

این راهنما برای نشت احتمالی credential، دسترسی غیرمجاز، خرابی Adapter و یافته امنیتی بحرانی است. هیچ Secret در ticket، chat، log یا Git ثبت نشود.

## مهار فوری

1. اتصال آسیب‌دیده را از صفحه صرافی «غیرفعال» و سپس با step-up «حذف قطعی کلید» کنید. این کار ciphertext، permission و امکان اجرا را حذف می‌کند.
2. در پنل خود صرافی کلید را revoke کنید؛ تنها حذف داخل CryptoSniper کافی نیست.
3. همه نشست‌های ناشناس را ببندید و رمز حساب را تغییر دهید. اگر احتمال افشای keyring وجود دارد، نسخه جدید `EXCHANGE_CREDENTIAL_KEYS` را در secret store نصب، credentialهای سالم را rotate و نسخه قدیمی را پس از تأیید حذف کنید.
4. سرویس سفارش را pause کنید. فعال‌سازی Live در این نسخه مجاز نیست؛ Binance فقط read-only است.

## بررسی بدون انتشار داده خصوصی

- بازه رخداد، correlation ID، user/account ID داخلی و event typeهای Audit را ثبت کنید.
- logها را فقط از مسیر کنترل‌شده بررسی کنید؛ canary یا secret را در فرمان shell تکرار نکنید.
- `uv run python scripts/security_scan.py`، `uvx pip-audit==2.9.0` و مجموعه `tests/test_security_stage17.py` را اجرا کنید.
- وضعیت یافته را با شدت `critical/high/medium/low` و یکی از `open/mitigated/accepted` ثبت کنید. یافته باز critical/high مانع Release است.

## بازیابی اتصال

کلید تازه باید withdrawal خاموش، حداقل permission لازم و در صورت امکان IP allowlist داشته باشد. پس از ذخیره، sync مجوزها را اجرا کنید؛ تا `can_withdraw=false` و read/trade مورد انتظار تأیید نشود `trading_enabled` فعال نمی‌شود. نتیجه ناشناخته سفارش هرگز موفق فرض نمی‌شود و باید از دفتر provider reconcile شود.

## اطلاع‌رسانی و نگهداری

در گزارش رخداد، داده شخصی و متن Signal را کمینه کنید. Audit در بازه سیاست نگهداری append-only است؛ reset token و session منقضی طبق job روزانه پاک می‌شوند. زمان مهار، rotation، scope داده، علت، اصلاح و آزمون regression را ثبت کنید.
