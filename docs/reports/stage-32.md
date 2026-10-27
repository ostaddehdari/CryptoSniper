# Stage32 — تکمیل سیگنال و تلگرام

وضعیت: هر پنج ورک، CI دقیق و انتشار immutable تکمیل است؛ نصب VPS و پذیرش credential واقعی جداگانه باز هستند (`partial`).

- W01: مجموعهٔ نسخه‌دار سیگنال‌های برچسب‌خوردهٔ فارسی/انگلیسی، گزارش تکرارپذیر کیفیت و جداسازی confidence فنی از کامل‌بودن داده. متن مبهم یا ناقص به معامله نمی‌رود.
- W02: ویرایش با دلیل اختیاری و audit، چرخهٔ تکی/گروهی owner-scoped، و «تأیید و انتقال» idempotent که snapshot دقیق تأییدشده را داخل فرم دستی می‌گذارد.
- W03: ارسال مجدد کد، وضعیت انقضا/تلاش، 2FA، FloodWait و آرشیو قابل‌ادامه با cursor پایدار. پیام تاریخی هرگز اتوماسیون معامله را فعال نمی‌کند.
- W04: سیاست قابل‌ویرایش Template/AI/Hybrid، قالب نسخه‌دار، کلید AI فقط در environment و schema سخت‌گیرانه. خروجی ناشناخته/نامعتبر مدل `INVALID` می‌شود و سفارش را فعال نمی‌کند.
- W05: شروع/ادامهٔ ارزیابی، نتیجه و آمار کانال، بایگانی خودکار no-entry قدیمی و روش محافظه‌کارانهٔ OHLC. ترتیب درون کندل نامعلوم است و برخورد مبهم سود قطعی محسوب نمی‌شود.

ظاهر پایهٔ React/Cornix حفظ شده است؛ blob فایل `styles.css` همان `565980a9a4a5ba390f09fcc61c5a6ea9a6a82cdd` است. Full-Auto تلگرام فقط Simulator/Paper است. `LIVE_TRADING_ENABLED` و `LIVE_EXIT_MANAGEMENT_ENABLED` همچنان پیش‌فرض خاموش‌اند.

## شواهد نهایی

- کاندید `b7306b323ea99baea1e6ebd8899de873fb62d4c7` در PostgreSQL/Redis با ۷۵۲ آزمون بدون failure/skip پاس شد.
- React: دو تست، build تولیدی و smoke مرورگر در چهار عرض 320/390/768/1440 موفق بود؛ Celery و migration check نیز در همان اجرا پاس شدند.
- lint/format، security scan، dependency audit، Django check و ۸۱ آزمون محلی نصب‌کننده موفق‌اند.
- CI نهایی: https://github.com/ostaddehdari/CryptoSniper/actions/runs/40469881498؛ evidence artifact `12718007967`.
- آزمون حساب واقعی Telegram و provider هوش مصنوعی انجام نشده، چون credential مجاز ارائه نشده است. نبود credential با موفقیت قراردادی جایگزین یا پنهان نمی‌شود.

## تحویل

- Branch: `stage32-final-signals` روی `stage31-final-management`؛ ادغام main انجام نشده است.
- Release: https://github.com/ostaddehdari/CryptoSniper/releases/tag/stage32-react-v0.32.0rc1-deploy-r1
- ZIP SHA256: `0bdfb164914c6b8d3aa0bbb5997941d34f48762faeeea1d24d8ba9188cfa70a6`
- Installer SHA256: `de88fb197ccc1ec8a3bfaf428dd8ce982c5fc661497f9315b1bc737ac0ae3566`
- دانلود مستقل assetها و اجرای installer با `--check` موفق بود و هیچ نصب واقعی انجام نشد.
- راهنمای عملیات در `docs/stage32-operator.fa.md` است.
- استیج بعد S33 است و در این تحویل آغاز نشده است.
