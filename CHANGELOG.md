## v0.10.0rc1 — استیج‌های ۹ و ۱۰ (۱۶ اکتبر ۲۰۲۶)

## 0.12.0rc1 — 2026-10-17

- S11: seven queues, leased Beat, durable Paper provider receipts, fenced recovery, bounded retry/dead-letter, reconciliation, read-only External observations and owner operations center.
- S12: fixed-reference crossing/proximity/profit alerts, central in-app/browser notifications with permission and read receipts, Watchlist indicators and private UI/API.
- Cumulative installer preserves managed settings/data and backs up systemd units; real Binance order writes remain disabled. 110 tests and real browser/Worker CI passed on 21b8b52; cumulative Release and installer --check published. VPS acceptance pending.


- مدل مستقل TP targets، توزیع Decimal و rounding به هدف آخر؛ دفتر Fill خروج و کنترل حد موجودی.
- اجرای مرحله‌ای Paper TP/SL، Move to Entry/previous TP/manual SL با audit، بدون Native stop.
- Percentage Trailing فعال‌شونده در TP1 با High-water پایدار؛ تقدم آن بر TP Sell و جلوگیری از فروش مضاعف.
- سناریوی Tick دستی فقط برای Paper، پایش مستقل Celery و تشخیص فید قدیمی؛ دستور واقعی Binance همچنان غیرفعال.
- ۸۶ تست CI موفق و انتشار ZIP تجمعی با SHA256. استقرار VPS تا ارائه لاگ کاربر تأیید نشده.

# تاریخچه تغییرات

## 0.3.0rc1 — استیج ۳، ۱۶ اکتبر ۲۰۲۶

- کاتالوگ صرافی، Asset، بازار Spot/Margin، حساب خصوصی کاربر و Snapshot موجودی.
- رمزنگاری authenticated از نوع AES-256-GCM با key version، گردش کلید و نگهداری کلید خارج Database.
- قرارداد Adapter کامل و شبیه‌ساز Paper برای موجودی، قیمت، سفارش، Fill و Cancel.
- Adapter خواندنی Binance برای بررسی مجوز، رد Withdrawal، موجودی، Market metadata و قیمت؛ ارسال سفارش واقعی مسدود است.
- مرکز صرافی واکنش‌گرا، فرم اتصال امن، وضعیت مجوزها، موجودی و جدول محدودیت بازار.
- تأیید Provider واقعی تا انتخاب صرافی نهایی و ارائه کلید آزمایشی/مجاز در وضعیت pending باقی می‌ماند.

## 0.2.0 — استیج ۲، ۷ اکتبر ۲۰۲۶

- پروفایل خصوصی با ایمیل یکتا، نام نمایشی، منطقه زمانی، ارز پایه، وضعیت حساب و ظاهر.
- بازیابی رمز یک‌بارمصرف و انقضادار، ثبت و ابطال نشست‌ها و خروج امن.
- rate limit ورود، CSRF، API خصوصی مبتنی بر Session و رد حساب تعلیق‌شده.
- پیش‌فرض‌های معامله Spot/Margin، توزیع TP برابر ۱۰/۱۰/۸۰ و هر دو Trailing فعال.
- Audit افزایشی با هش IP و پوشاندن داده‌های حساس، همراه رابط تنظیمات و امنیت.

## 0.1.0 — استیج ۱، ۶ اکتبر ۲۰۲۶

- ساخت پروژه Django و محیط‌های توسعه، Staging و Production با وابستگی‌های قفل‌شده.
- PostgreSQL، Redis و migration اولیه مدل کاربر قابل توسعه؛ تمام زمان‌ها UTC.
- Celery و Beat، Workerهای صف سفارش و گزارش، heartbeat و ثبت نتیجه probe در پردازش مستقل.
- رابط فارسی RTL روشن برای موبایل و دسکتاپ؛ Dark اختیاری؛ ورود، خروج، پروفایل بازشونده و وضعیت سرویس‌ها.
- health/readiness، correlation ID، لاگ JSON با پوشاندن اسرار و حفاظت CSRF/نشست.
- CI، ۱۶ آزمون و smoke سرویس‌های واقعی و مرورگر؛ راهنمای نصب بدون نیاز به Node runtime.

این نسخه پایه هنوز موتور معامله، اتصال واقعی صرافی یا سیگنال تلگرام ندارد. Telethon و تحلیل قالبی/AI فقط در استیج ۲۱ اجرا خواهند شد.
