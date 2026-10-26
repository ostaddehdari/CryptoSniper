# Stage29 — بازگردانی رابط اصلی React

وضعیت: کد و بسته در شاخه آماده‌اند؛ ادغام main و پذیرش سرور واقعی در انتظار است. به همین علت وضعیت کلی partial است.

## پنج ورک

- W01: ادغام React Stage25 با main، حفظ migrationها و ثبت S29 تا S33؛ نگاشت درخواست‌ها در final-delivery-checklist.fa.md.
- W02: سایدبار نهایی، دو تب معامله جدید، خروج POST و بازیابی لینک قدیمی/ناشناخته.
- W03: سبک پایه با blob 565980a9a4a5ba390f09fcc61c5a6ea9a6a82cdd حفظ شد؛ دارایی نسخه‌دار، PWA static-only، حذف فقط cacheهای خود برنامه و توقف درخواست آفلاین.
- W04: Build، دو Node route test، Ruff، Django check، Security و 62 رگرسیون نصب‌کننده محلی موفق. CI با PostgreSQL/Redis شامل 336 testcase موفق، smoke مرورگر account→market→chart→draft، نمودار سیگنال/معامله و ناوبری/خروج POST است. عرض‌های320/390/768/1440 بدون overflow افقی بررسی شدند؛ تصاویر 1440 و320 بازبینی شدند.
- W05: Release تجمیعی از SHA موفق CI، ZIP، SHA256، release.json، نصب‌کننده --check و deploy.sh با pin همان فایل‌های منتشرشده.

## شواهد

- Source: 69fb18cc5591ecbd8f80f648c8ad0ed0c45545ae
- CI: https://github.com/ostaddehdari/CryptoSniper/actions/runs/40342500209
- Evidence artifact: 12659028621
- Release: https://github.com/ostaddehdari/CryptoSniper/releases/tag/stage29-react-v0.29.0rc1-deploy-r1
- ZIP SHA256: 5271407b985ea0b47dfa400fbc7cacab89167156191759c8eed0f08fc2dab1e1
- Installer SHA256: 45aa55e3c494fa0ddb878cca261e6cc8825220cba7e5dcc4d68eb039c77b8ad7
- PR: https://github.com/ostaddehdari/CryptoSniper/pull/3

## محدودیت‌ها

- ارسال مستقیم main توسط بررسی خودکار به دلیل نبود تأیید صریح آن اقدام رد شد؛ شاخه و PR آماده‌اند.
- تصاویر/داده CI با حساب و کندل تست هستند و اثبات اتصال یا معامله واقعی نیستند.
- تطابق تصویری با دامنه تأییدشده توسط صاحب‌کار و نصب روی VPS هنوز انجام نشده است.
- قالب‌های قدیمی برای سازگاری Backend باقی‌اند؛ مسیرهای اصلی رابط React را ارائه می‌کنند.
- قابلیت‌های معامله، سیگنال و موجودی باقی‌مانده طبق S30 تا S33 تکمیل می‌شوند؛ این مراحل شروع نشده‌اند.
- اسرار، کلیدهای رمزنگاری، حساب‌ها و داده قبلی در ارتقا حفظ می‌شوند؛ فعال‌سازی معامله واقعی انجام نشده است.

## اصلاحیه r2 — ناسازگاری schema نصب قدیمی

گزارش واقعی اپراتور نشان داد r1 در accounts.0007_walletconnection با DuplicateTable متوقف و فایل‌های برنامه rollback شدند؛ بنابراین پذیرش نصب r1 ناموفق است.

r2 قبل از migration پشتیبان خصوصی pg_dump می‌گیرد؛ جدول/ستون‌های موجود React را از نظر نوع، null، PK، FK و unique بررسی و فقط schema سازگار را adopt می‌کند. indexهای قدیمی حفظ و نام canonical لازم اضافه می‌شود؛ داده‌ای حذف یا بازنویسی نمی‌شود. اختلاف ساختار موجب توقف تراکنشی می‌شود؛ --fake عمومی استفاده نمی‌شود. migrationهای تاریخی دست‌نخورده‌اند.

آزمون‌های PostgreSQL این اصلاح: حفظ ردیف کیف پول با index قدیمی، عدم پذیرش schema ناسازگار، dry-run بدون تغییر، diagnostics نیمه‌موجود، نصب تازه و تکرارپذیری. پذیرش اجرای r2 روی سرور اپراتور پس از ارسال لاگ جدید مشخص می‌شود.
