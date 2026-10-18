# گزارش استیج ۲۱ — Telethon، تحلیل کانال و پنج صرافی Spot

تاریخ: 2026-10-18

نسخه: `0.21.0rc1`

وضعیت: `partial`

## خروجی پنج ورک

| ورک | خروجی کد | وضعیت پذیرش |
|---|---|---|
| W01 | ورود API ID/hash، کد و 2FA؛ session رمزنگاری‌شده AES-GCM و revoke | آزمون محلی پاس؛ حساب واقعی Telegram ارائه نشده |
| W02 | listener دائمی، catch-up محدود، new/edit/delete، cursor و dedup | fixture پاس؛ کانال واقعی ارائه نشده |
| W03 | قالب bounded برای هر کانال و fallback به parser قطعی | نمونه محلی پاس؛ corpus واقعی ارائه نشده |
| W04 | provider سازگار OpenAI با structured schema، timeout و مرز prompt-injection | نبود provider/key صریحاً blocked است |
| W05 | UI کانال و سیاست‌های Paper؛ پنج adapter Spot و outbox سفارش Live | قرارداد و fixture پاس؛ credential/provider واقعی آزمون نشده |

## پوشش صرافی‌ها

| صرافی | داده عمومی | داده شخصی | سفارش Spot | وضعیت واقعی |
|---|---|---|---|---|
| Nobitex | بازار، ticker، orderbook | کیف پول و سفارش‌ها | API رسمی؛ testnet قابل انتخاب | `partial`؛ token محدود واقعی موجود نیست |
| LBank | دقت بازار، ticker، orderbook | موجودی و سفارش‌ها | Spot V2 با HmacSHA256 | `partial`؛ API key واقعی موجود نیست |
| WEEX | exchangeInfo، ticker، depth | account/balance/order | Spot V3 با passphrase و HMAC Base64 | `partial`؛ API key واقعی موجود نیست |
| Ourbit | exchangeInfo، ticker، depth | account/balance/order | Spot V3 با HMAC query | `partial`؛ API key واقعی موجود نیست |
| Bitunix | pairs، price، depth | account/order | Spot V1 با double-SHA256 | `partial`؛ API key واقعی موجود نیست |

## کنترل‌های ایمنی و شواهد

- secretها رمزنگاری می‌شوند و در log، URL یا HTML بازگردانده نمی‌شوند.
- task پیش از write مجوز provider را دوباره می‌سنجد؛ کلید برداشت‌دار رد می‌شود.
- نتیجه نامعلوم سفارش retry نمی‌شود. Live و Full-Auto پیش‌فرض خاموش‌اند؛ Full-Auto فقط Paper است.
- Ruff، compileall، Django system check و migration drift پاس شدند؛ ۱۷ آزمون adapter/Telegram و ۲ آزمون قرارداد نصب‌کننده پاس شدند.
- exact-source CI روی commit `e315e1983bb916ed8867a721b583e9b2c55eb93a` هر ۲۴۵ آزمون، PostgreSQL/Redis، هفت Worker/Beat و Chromium smoke را پاس کرد.
- Release تجمیعی 0.21 با ZIP/installer/SHA256SUMS و `CHECK_OK` منتشر شد؛ SHA فایل ZIP `8a44ba2e8e1d61806a122d93bf92f6e3eccc85fa291fc3f51c327469141e0d41` است.
- نصب VPS و اتصال‌های واقعی هنوز شواهد ندارند، بنابراین استیج `partial` می‌ماند.
