## 0.16.0rc1 — استیج‌های ۱۵ و ۱۶ (2026-10-17)

- P/L مالی Decimal با gross/net، تبدیل fee asset، بهره/بازپرداخت Margin و policy صریح unknown؛ آمار با breakeven ثابت و win-rate مستند.
- aggregateهای idempotent روز/هفته/ماه بر اساس timezone و تفکیک coin/exchange/source، cache versioned و rebuild مستقل در صف reports.
- مرکز گزارش با فیلتر، drill-down، CSV مقاوم در برابر formula injection و نمودار SVG هم‌منبع.
- navigation و کارت‌های موبایل، فرم‌های سازگار با کیبورد و draft فقط در history، جدول/کارت Trades و تنظیمات یکپارچه؛ Telegram/AI همچنان S21.
- PWA با cache فقط static، بدون cache داده خصوصی یا صف POST؛ offline submit متوقف می‌شود و پس از اتصال replay خودکار ندارد.
- نصب Stage14 توسط لاگ اپراتور تأیید شد. Release تجمیعی Stage16 پس از CI دقیق منتشر می‌شود؛ real Binance writes و Margin/Short خاموش‌اند.

## 0.14.0rc1 — استیج‌های ۱۳ و ۱۴ (2026-10-17)

- Dashboard با موجودی و ارزش‌گذاری دارای زمان/نرخ، P/L مشترک Fill/fee، شاخص‌های timezone، نمایش موبایل/دسکتاپ و refresh جزئی با خطای واضح.
- Open Trades و History با فیلتر و صفحه‌بندی، جزئیات raw/parsed/Plan/Orders/Fills و timeline محدود و امن، External فقط‌خواندنی.
- بستن باقی‌ماندهٔ Paper با تأیید، UUID و درخواست پایدار، orders Worker و قفل مشترک SL/TP؛ انتظار قیمت و منع اقدام روی نتیجه نامعلوم؛ audit و کنترل نسخهٔ SL/trailing و توقف ورود.
- ۱۳۷ تست، PostgreSQL/Redis/هفت Worker/Beat/Chromium، بستن تأییدشده در Worker و offline/reconnect و UI موبایل/دسکتاپ پاس شدند؛ سنجه workload کوچک Dashboard: ۱۶ query و ۲۵٫۷۶ms.
- نصب‌کننده تجمیعی Stage14، حفظ تنظیمات/داده/کلید و پشتیبانی headerهای دقیق Stage01–14؛ ۱۲ آزمون Nginx بدون تغییر سرویس واقعی.
- نصب Stage12 r1 توسط لاگ اپراتور تأیید شد. نصب نسخه 0.14 و پذیرش Binance واقعی باز است؛ real orders و Margin/Short خاموش می‌مانند.

## v0.10.0rc1 — استیج‌های ۹ و ۱۰ (۱۶ اکتبر ۲۰۲۶)

## 0.12.0rc1 — installer r1 (2026-10-17)

- Fixed Stage10-managed Nginx snippets being rejected during the Stage12 upgrade.
- Recognize exact managed headers for Stage01–12, keep rejecting unmanaged/lookalike files, and refuse a snippet changed between plan and apply.
- Six installer regression tests passed on temporary files: every managed version, Stage10 upgrade/rollback, fresh routing, unmanaged headers and concurrent edits. Application ZIP/source is unchanged.
- Operator log confirms the original upgrade stopped before application/data replacement. A subsequent operator log at 15:11 UTC confirms r1 installed successfully; public-browser acceptance remains pending.


## 0.12.0rc1 — 2026-10-17

- S11: seven queues, leased Beat, durable Paper provider receipts, fenced recovery, bounded retry/dead-letter, reconciliation, read-only External observations and owner operations center.
- S12: fixed-reference crossing/proximity/profit alerts, central in-app/browser notifications with permission and read receipts, Watchlist indicators and private UI/API.
- Cumulative installer preserves managed settings/data and backs up systemd units; real Binance order writes remain disabled. 110 tests and real browser/Worker CI passed on 21b8b52; cumulative Release and installer --check published. Stage12 installation confirmed by the subsequent operator log; public-browser acceptance pending.


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
