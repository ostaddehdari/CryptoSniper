# گزارش استیج ۲۲ — تکمیل Telegram و ارزیابی تاریخی

تاریخ: 2026-10-18

نسخه: `0.22.0rc1`

وضعیت: `partial`

| ورک | خروجی | شواهد محلی | پذیرش خارجی |
|---|---|---|---|
| W01 | وریفای کد/2FA، resend/expiry/attempt limit و رمزنگاری | تست عدم persist کد و schema check | حساب واقعی لازم است |
| W02 | backfill کامل، snapshot/cursor و pause/resume | قرارداد منع automation تاریخی | کانال واقعی و FloodWait لازم است |
| W03 | چندقالبی و دسته‌بندی پنج‌گانه | تست priority/marker و parser | corpus برچسب‌خورده لازم است |
| W04 | OHLC و outcome محافظه‌کارانه | تست entry-first، long/short و ambiguous | صحت provider مقصد جداست |
| W05 | analytics/API خصوصی و بسته تجمعی | ۲۶۰ تست exact-source و Release موفق | نصب و پذیرش VPS در انتظار است |

هیچ نتیجه تاریخی سفارش ایجاد نمی‌کند. `LIVE_TRADING_ENABLED=false` و Full-Auto محدود به Simulator Paper باقی می‌مانند.

CI دقیق منبع روی commit `cfce4d3a19f0bc2df56aae15175b80255a940f51` با ۲۶۰ آزمون، PostgreSQL، Redis، Worker/Beat و Chromium موفق شد. Release تغییرناپذیر `stage22-v0.22.0rc1-deploy` منتشر شد؛ SHA-256 فایل ZIP برابر `8614ebae00367167dbe1f3144db559e194304783b185f1fd3a59dc324e91563a` و نصب‌کننده برابر `5ce7a432df677af03ff910df0e9ba39a93d4c53530d388a686fb358621c3b251` است. این شواهد جای آزمون حساب واقعی Telegram، کانال مقصد، credential صرافی یا پذیرش VPS را نمی‌گیرد.
