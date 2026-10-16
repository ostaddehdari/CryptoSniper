# گزارش استیج ۳ — نسخه 0.3.0rc1

واحد اجرا: پنج ورک S03. مخزن `ostaddehdari/CryptoSniper`، شاخه `main`؛ تاریخ ۱۶ اکتبر ۲۰۲۶. وضعیت: `partial` فقط به‌علت نبود انتخاب نهایی Provider و credential آزمایشی/مجاز برای بررسی خارجی.

## نتیجه ورک‌ها

| ورک | نتیجه |
|---|---|
| S03-W01 | مدل‌های Exchange، Asset، ExchangeMarket، UserExchangeAccount و BalanceSnapshot با محدودیت Spot/Margin و مالکیت کاربر ساخته شدند. |
| S03-W02 | API key/secret/passphrase با AES-256-GCM، AAD وابسته به کاربر/صرافی، key version و rotation رمزنگاری شدند؛ Secret در API یا HTML بازگردانده نمی‌شود. |
| S03-W03 | قرارداد مستقل Adapter و شبیه‌ساز Paper برای balance/market/ticker/order/fill/cancel و idempotency پایه ساخته شد. |
| S03-W04 | Adapter خواندنی Binance با امضای HMAC، بررسی `enableReading`، `enableSpotAndMarginTrading` و رد قطعی `enableWithdrawals=true` ساخته شد. تست قرارداد با transport ساختگی پاس شده؛ تست حساب واقعی به credential مجاز نیاز دارد. |
| S03-W05 | Worker همگام‌سازی، Market metadata، precision، min notional، Snapshot موجودی، API خصوصی و UI کامل موبایل/دسکتاپ ساخته شد. |

## ظاهر قابل مشاهده

- `/exchanges/`: داشبورد اتصال‌ها، کاتالوگ Spot/Margin و وضعیت امنیت.
- `/exchanges/add/`: فرم افزودن شبیه‌ساز یا حساب واقعی با راهنمای مجوز.
- `/exchanges/<id>/`: وضعیت مجوزها، موجودی، بازارها و محدودیت‌ها.
- Dashboard اصلی تعداد اتصال‌ها را نمایش می‌دهد و منوی «صرافی‌ها» اضافه شده است.

## بررسی‌های محلی انجام‌شده

| بررسی | نتیجه |
|---|---|
| Ruff کل backend/tests/scripts | موفق |
| Django system check | موفق |
| `makemigrations --check --dry-run` | بدون تغییر؛ PostgreSQL محلی در این محیط در دسترس نبود و warning اتصال ثبت شد |
| ۷ تست خالص قرارداد Simulator و Binance | موفق |
| secret redaction و ciphertext | موفق روی PostgreSQL در CI |
| Browser smoke | موفق روی Chromium در desktop و عرض‌های ۳۲۰، ۳۹۰ و ۷۶۸ پیکسل |

## شواهد CI نهایی

- [GitHub Actions Run #8](https://github.com/ostaddehdari/CryptoSniper/actions/runs/38896560818): موفق روی commit `8945272bace438ae110455b281b1ff95eddd59be`.
- ۵۳ تست Pytest روی PostgreSQL واقعی: ۵۳ موفق، صفر failure/error/skip.
- Redis، سه Worker مستقل، Beat، HTTP readiness و smoke مرورگر همگی موفق.
- artifact شماره `12044127815` با SHA-256 برابر `4696adb98920df0273a534209f70925bf79d640f652e75f81c4c0e3c7d15ea10` شامل JUnit و ۱۰ screenshot دسکتاپ/موبایل است.

## مرز امنیتی

- اجرای سفارش واقعی در Binance Adapter عمداً با `UnsupportedOperationError` مسدود است.
- حالت پیش‌فرض Paper است و Futures/Perpetual در مدل و UI قابل اجرا نیست.
- Withdrawal permission باعث رد اتصال می‌شود.
- API Key/Secret کاربر نباید در issue، chat، git یا گزارش تست قرار گیرد.

## منابع قرارداد Provider

- [Binance Spot REST API security](https://developers.binance.com/en/docs/products/spot/rest-api)
- [Binance API Key permission endpoint](https://developers.binance.com/en/docs/catalog/core-trading-wallet/api/rest-api/account)

## مانع باقی‌مانده

کاربر باید صرافی هدف نخست را تأیید کند. اگر Binance انتخاب شد، بررسی فقط‌خواندنی با کلیدی که Withdrawal آن خاموش و ترجیحاً IP-restricted است در محیط امن سرور انجام می‌شود. اگر Provider دیگری انتخاب شود، Adapter اختصاصی همان Provider در همین S03 جایگزین/اضافه و سپس استیج done می‌شود.
