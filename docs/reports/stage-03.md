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

## شواهد استقرار روی سرور کاربر — ۲۰۲۶/۱۰/۱۶

طبق خروجی نصب ارسالی کاربر از Ubuntu 24.04 سرور `5.61.27.185` (این بخش مشاهدهٔ مستقیم CI نیست):

- بستهٔ منتشرشده `stage03-v0.3.0rc1-deploy` با کنترل دو SHA-256 نصب شده است.
- Django system check: بدون مشکل؛ Migrationها از جمله `exchanges.0001_initial` از نصب قبلی اعمال شده بودند.
- Readiness برنامه: PostgreSQL و Redis cache/broker/results همگی `true`.
- بررسی مستقل Workerهای orders و reports و heartbeat Beat: موفق؛ سرویس‌های `cryptosniper-redis/web/orders/reports/beat` فعال.
- پس از اصلاح کنترل Reload ناهمزمان Nginx: نخستین probe وضعیت HTTPS `404` و probe دوم `200` شد؛ مسیر HTTPS ورود هم `200` پاسخ داد.
- خروجی نهایی نصب‌کننده: `INSTALL_OK: CryptoSniper Stage03 v0.3.0rc1` و `DEPLOY_OK`.
- Scope تأیید: **Nginx origin روی localhost و سرویس‌های سرور**. این گزارش جای آزمون دستی مرورگر از اینترنت عمومی یا بررسی Provider واقعی را نمی‌گیرد.

**باقیماندهٔ رسمی S03-W04:** انتخاب صرافی نخست و آزمون حساب مجاز (ترجیحاً API فقط‌خواندنی و IP-restricted، قطعاً بدون Withdrawal). در غیاب این شواهد، وضعیت Stage 03 همچنان `partial` است و Stage 04 هنوز آغاز نشده است. هرگز Secret را در GitHub یا گزارش‌ها قرار ندهید.

## انتخاب رسمی نخستین Provider

در ۱۶ اکتبر ۲۰۲۶ کاربر **Binance** را به‌عنوان اولین صرافی هدف تأیید کرد. Adapter خواندنی Binance از قبل موجود است. مانع «انتخاب Provider» برطرف شد؛ ولی **آزمون واقعی مجوز و پاسخ حساب** تا ورود کلید مجاز در UI خود سرور همچنان انجام نشده است. نه کلید را در چت ارسال کنید و نه حق برداشت را فعال کنید. S03-W04 و وضعیت رسمی S03 تا دریافت شواهد تست حساب واقعی همچنان `partial` است. با درخواست صریح کاربر، توسعهٔ مستقل S04 آغاز می‌شود ولی تکمیل رسمی آن تا رفع پیش‌نیاز S03 ثبت نخواهد شد.
