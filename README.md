# CryptoSniper

سامانه پایتونی دریافت، اجرای و مدیریت سیگنال رمزارز با Django، PostgreSQL، Redis و Celery، رابط Mobile-First و حالت روشن پیش‌فرض.

**برنامه: ۲۱ استیج × ۵ ورک = ۱۰۵ ورک.** واحد اجرا در هر درخواست، یک استیج کامل با همه ورک‌هایش است. **استیج ۱ با هر پنج ورک تکمیل شده است.** ۱۶ تست و آزمون مستقل Worker و رابط موبایل/دسکتاپ در GitHub Actions موفق بودند. استیج بعد S02 است.

- [گزارش تحویل و شواهد استیج ۱](docs/reports/stage-01.md)
- [راهنمای نصب و اجرای استیج ۱](docs/setup.md)
- [بررسی خودکار در GitHub Actions](https://github.com/ostaddehdari/CryptoSniper/actions)

- [برنامه کامل استیج‌ها و ورک‌ها](docs/roadmap.md)
- [پروتکل اجرای یک‌باره هر استیج و ثبت کامیت](docs/execution-protocol.md)
- [قواعد معماری و معامله](docs/architecture.md)
- [نگاشت تمام بخش‌های پروپوزال](docs/requirements-traceability.md)
- [برنامه ماشینی](docs/plan.json) و [وضعیت اجرا](docs/progress.json)
- [متن اصلی پروپوزال](docs/source/proposal-original.txt)

نسخه نخست: Spot و Margin؛ Futures و Perpetual برای آینده. Manual Entry و Smart Paste در نسخه پایه آماده می‌شوند. **اتصال Telethon، خواندن کانال‌ها و تحلیل قالبی یا هوش مصنوعی فقط آخرین استیج، S21، هستند.**

برای ادامه:

> استیج ۲ CryptoSniper را با همه ورک‌هایش طبق برنامه مخزن کامل بساز، تست‌های مرتبط را اجرا کن و در GitHub کامیت و push کن.

پس از اتمام، همین دستور با شماره استیج بعد اجرا می‌شود. درخواست یک استیج مجوز رفتن خودکار به استیج بعد نیست. ثبت کد در GitHub به‌معنی مجوز اجرای معامله با پول واقعی یا استقرار روی سرور تعیین‌نشده نیست.

اجرای کامل نیازمند هاست پایتونی با Worker دائمی، PostgreSQL، Redis، scheduler و HTTPS است. Production نیازی به runtime Node.js ندارد.
