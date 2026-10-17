# استیج ۱۶ — تجربهٔ موبایل، دسکتاپ و PWA | 0.16.0rc1

هر پنج ورک تجربهٔ کاربری روی همان داده و کنترل‌های مالک پیاده‌سازی شده‌اند. PWA عمداً فقط فایل‌های static را cache می‌کند؛ navigation خصوصی، API، گزارش مالی و POST معاملاتی cache یا در صف offline قرار نمی‌گیرند.

| ورک | نتیجه |
|---|---|
| S16-W01 | navigation پایین موبایل، کارت Watchlist، میانبر Reports و login دسترس‌پذیر؛ Light پیش‌فرض و Dark اختیاری حفظ شد. |
| S16-W02 | فرم Manual و Smart Paste یک‌دستی با input mode عددی، submit bar سازگار با کیبورد و draft محدود به `history.state` همان history entry؛ بدون localStorage/Cache. |
| S16-W03 | جدول دسکتاپ و کارت موبایل برای Trades، facts حیاتی market/side/trailing/P&L و timeline معنایی؛ مقادیر واقعی model نمایش داده می‌شوند. |
| S16-W04 | تب‌های یکپارچه Settings، رابط source و Reports/Alerts؛ Telegram و channel/AI قابل فعال‌سازی نیستند و تا S21 باقی می‌مانند. |
| S16-W05 | manifest، icon و service worker static-only، banner آفلاین، جلوگیری از submit آفلاین بدون replay خودکار، focus-visible و forced-colors. |

## امنیت آفلاین و بازیابی فرم

Service Worker تنها درخواست `GET` هم‌مبدأ زیر static prefix را می‌بیند. درخواست navigation، API و هر روش غیر GET مستقیماً به شبکه می‌رود و Background Sync/IndexedDB برای عملیات مالی وجود ندارد. در حالت offline، submit از UI متوقف و پیام روشن نمایش داده می‌شود؛ پس از reconnect کاربر باید دوباره اقدام را آگاهانه تأیید کند.

فرم فقط مقادیر غیرحساس همان history entry را در `history.state` نگه می‌دارد. password، token، secret، CSRF و file ذخیره نمی‌شوند. برخورد فیلد Smart Paste با نام `method` در اجرای واقعی Chromium شناسایی شد؛ خواندن روش اکنون از attribute فرم انجام می‌شود و تست ثابت از بازگشت خطا جلوگیری می‌کند.

## شواهد و محدودیت‌ها

- CI اولیه **۱۴۹ تست** را گذراند و خطای browser را آشکار کرد. [CI موفق پس از اصلاح](https://github.com/ostaddehdari/CryptoSniper/actions/runs/39055497955) روی commit `e1d376b75b329d8b80016da17a4811951faf0a59`: **۱۵۰ تست**، PostgreSQL/Redis، هفت Worker/Beat و Chromium؛ artifact شواهد `12109002649`.
- سنجهٔ همان اجرای موفق: `dashboard_queries=17` و `dashboard_build_ms=26.61` برای workload کوچک CI. این اعداد تضمین ظرفیت production نیستند.
- نصب Stage14 با لاگ اپراتور، حفظ داده/کلید/login، سلامت ده سرویس و HTTP 200 محلی Nginx تأیید شده است. نصب Stage16 و پذیرش مرورگر عمومی هنوز باید توسط اپراتور انجام شود.
- اجرای واقعی Binance، Margin/Short و External management خاموش است؛ Telegram/AI تنها در S21 اجرا می‌شود.

