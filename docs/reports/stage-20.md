# گزارش استیج ۲۰ — پذیرش نسخه پایه و تحویل

وضعیت: `partial`. هر پنج ورک محصول پایه روی Paper/Simulator پیاده‌سازی شده‌اند؛ پذیرش هدف VPS و بسته نهایی هنوز باز است.

| ورک | تحویل |
|---|---|
| S20-W01 | مسیر UI واقعی Manual و Smart Paste تا position close |
| S20-W02 | Spot/Margin Long/Short Simulator، TP 10/10/80، SL، Step و Percentage trailing |
| S20-W03 | alert/notification، fee/net، timeline، timezone و صفحات موبایل/دسکتاپ |
| S20-W04 | crash/duplicate/recovery، owner boundary، backup/restore و release security gate |
| S20-W05 | API قرارداد پذیرش، راهنمای کاربر/ادمین، checklist و changelog نسخه 0.20.0rc1 |

[CI منبع دقیق](https://github.com/ostaddehdari/CryptoSniper/actions/runs/39115544511) روی commit `3e938896d3cd82dfad16bc54c258d46031ce69be` با ۲۲۷ تست و smoke واقعی PostgreSQL/Redis/Workers/Beat/Chromium پاس شد. smoke مسیر Manual را تا close، alerts/notification/report/timezone، قطع مرورگر و ماندگاری receipt تأیید کرد. نتیجه Simulator شاهد Binance sandbox/live یا سودآوری نیست. real order write خاموش است؛ Futures/Perpetual خارج دامنه‌اند. Telegram، خواندن کانال، parser قالبی کانال و AI عمداً تا Stage21 پیاده‌سازی نشده‌اند و در این نسخه ادعا نمی‌شوند.

نسخه پایه «بدون تلگرام» از نظر دامنه کد کامل است، اما status به دلیل نصب‌نشدن بسته 0.20 روی VPS، نبود مرورگر عمومی مستقل و انجام‌نشدن restore/offsite واقعی `partial` باقی می‌ماند.

[Release رسمی 0.20](https://github.com/ostaddehdari/CryptoSniper/releases/tag/stage20-v0.20.0rc1-deploy) در [run بسته](https://github.com/ostaddehdari/CryptoSniper/actions/runs/39116144489) ساخته شد. ZIP با SHA-256 `a7264790d9f26d3d8cdb9727603b3d44982c7a040db1154edabef0f5bb83ce55` و installer با SHA-256 `fa1d8dac77191921f6f8a178eeeb6d62e6093d4792b59aa6501d04b9617896ed` دقیقاً در `scripts/deploy.sh` پین شده‌اند و `--check` محلی نیز همان bytes را تأیید کرد.
