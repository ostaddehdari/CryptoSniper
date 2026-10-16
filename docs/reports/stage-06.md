# Stage 06 — سیگنال و Inbox | v0.6.0rc1

تاریخ ۱۶ اکتبر ۲۰۲۶. وضعیت **partial** تا پایان CI و استقرار VPS؛ همچنین وابستگی‌های قبلی هنوز partial هستند.

| ورک | پیاده‌سازی |
|---|---|
| S06-W01 | SignalSource با تنها سه روش canonical: Manual، Smart Paste و Telegram (فقط placeholder برای Stage21). SourceTransport interface بدون اتصال خارجی. |
| S06-W02 | RawSignal با اصل متن و payload و SHA256، external_id scoped و revisionهای append-only برای حفظ متن نخستین و نسخه‌های بعدی؛ duplicate هم‌منبع دوباره سیگنال ایجاد نمی‌کند |
| S06-W03 | Signal، SignalTarget (۱ تا ۳ هدف)، confidence فنی، parser_version و immutable revision records، ارتباط مالکیت با کاربر و حساب/بازار |
| S06-W04 | وضعیت‌های New/Parsed/Needs Review/Approved/Rejected/Executed/Failed؛ transitionهای restricted با row lock، optimistic revision و audit، Executed/Failed رزرو شده برای engine |
| S06-W05 | Inbox فارسی RTL، مقایسه Raw/Structured، فیلتر status/source/date، اصلاح، Reject/Approve، API خصوصی و تاریخچه |

**امنیت:** ورود متن به معامله واقعی منجر نمی‌شود. Parser قالبی Stage07 و Telethon/AI Stage21 هستند. Approved Snapshot را تنظیمات بعدی تغییر نمی‌دهند. Confidence فنی «احتمال سود» نیست.

**محدودیت:** تست Provider واقعی Binance مرحله S03 و بندهای پذیرش قبلی هنوز کامل نشده‌اند. آزمون‌های CI و VPS باید مستند شوند و تا آن زمان Stage06 `partial` است.
