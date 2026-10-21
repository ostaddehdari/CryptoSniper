# گزارش استیج ۲۳

وضعیت: **partial — کدنویسی پنج ورک انجام شده، CI و نصب VPS در انتظار پذیرش هستند.**

## تحویل‌ها
- رابط React فارسی RTL و سایدبار جمع‌شونده روی shell اصلی.
- Dashboard واقعی با ارزش‌گذاری شناخته‌شده، USDT آزاد، حساب‌های متصل، سفارش‌های باز و P/L ماهانه در صورت وجود aggregate معتبر.
- صفحه معاملات یکپارچه برای `LiveSpotOrder` و `ExternalObservation` با حفظ حالت read-only برای External.
- Manual با account-scoped market list، quote همان بازار، TP/SL distance و Fix Loss Decimal.
- Smart Paste/Inbox جدید؛ reject reason اختیاری و edit reason اجباری.
- Exchanges به شکل جدول، فقط Live در UI جدید، Binance/simulator حذف از catalog جدید، حذف اتصال با revoke credential.
- Connection log مرحله‌ای Worker برای credentials/markets/balances بدون secret.
- راهنمای اتصال Bitunix، LBank، Nobitex، WEEX و Ourbit.
- Favorite assets سراسری با drag/drop و shortcut بازار→Manual.
- Telegram message search روی دادهٔ آرشیو و listener، کپی متن و انتقال مستقیم به Smart Paste.
- تنظیمات داخل محتوای اصلی با tabs افقی و جدا از sidebar.

## مواردی که عمداً ادعا نمی‌شوند
- full live TP/SL/trailing execution برای تمام providerها هنوز از این UI به‌تنهایی اثبات نشده است.
- اتصال self-custody wallet/on-chain اضافه نشده؛ «کیف پول» در این مرحله یعنی موجودی حساب صرافی/API.
- CI، Release و نصب VPS تا ثبت خروجی واقعی پذیرفته‌شده محسوب نمی‌شوند.
