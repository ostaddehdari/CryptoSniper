# تصمیم‌های اجرایی معماری و قواعد

این سند قواعد اجرایی برنامه را روشن می‌کند. متن اصلی پیوست بدون تغییر در `source/proposal-original.txt` محفوظ است. جزئیات زیر تصمیم طراحی‌اند و ادعای نقل عین پروپوزال نیستند.

## Stack و مرز مسئولیت

Python با نسخه پشتیبانی‌شده متناسب با هاست، Django، REST API، Django Templates، HTMX، Alpine.js و static CSS/JS. PostgreSQL منبع دائمی؛ Redis برای cache/queue/co-ordination؛ Celery/Beat برای پردازش مستقل. انتخاب نسخه دقیق و pin وابستگی‌ها در S01 با بررسی پشتیبانی رسمی انجام می‌شود. نسخه یا provider آزمایش‌نشده وعده قطعی محسوب نمی‌شود.

Frontend کنترل و نمایش است. ورود سفارش، TP، SL، trailing، alerts و recovery با بستن مرورگر متوقف نمی‌شوند. WSGI/polling فقط نمایش realtime را جایگزین می‌کند؛ جای Worker دائمی نیست. اگر هاست Worker ندارد، deployment باید process جدا در میزبان مناسب داشته باشد.

رابط موبایل مستقل و Mobile-First، Light اصلی و Dark اختیاری است. Desktop برای monitoring و تحلیل با navigation، top bar و workspace ساخته می‌شود. Node.js در Production الزامی نیست. ابزار build در development/CI در صورت نیاز قابل استفاده است.

## مرزهای نسخه نخست

Manual Entry، Smart Paste و در آخر S21 Telegram. Quick Signal و Quick Paste میان‌بر هستند. Watchlist منبع سیگنال نیست. Spot فقط long با دارایی موجود؛ Margin long/short تنها با borrow/repay و capabilities تأییدشده adapter. Futures/Perpetual غیرفعال؛ سیگنال futures با leverage بالا بی‌صدا به Margin تبدیل نشود.

ساختار چندکاربره و مالکیت داده از ابتدا برقرار است؛ امکانات commercial SaaS، copy trading، multi-entry، portfolio strategies و اپ native برای آینده‌اند. AI تحلیل کانال طبق درخواست جدید در S21 داخل scope است؛ AI پیش‌بینی سود یا معامله مستقل خارج قواعد موتور نیست.

## دیتابیس و انسجام

تمام جدول‌ها و فیلدهای پیشنهادشده در بخش ۴۱ متن مبنا باید در migration استیج مسئول پوشش داده شوند: users/user_settings؛ exchanges/user_exchange_accounts/exchange_markets/assets؛ signal_sources/telegram_sources/raw_signals/signals/signal_targets؛ trades/trade_targets/orders/order_fills/positions/trailing_rules/trade_events؛ price_alerts/notifications؛ watchlists/watchlist_items/balance_snapshots/daily_performance/audit_logs/idempotency_keys.

users/user_settings در S02، exchange و balance در S03، Watchlist در S04، draft trade در S05، signal در S06، order/position/event/idempotency در S08، targets در S09، trailing در S10، alert/notification در S12، aggregation در S15 و telegram_sources در S21 ساخته می‌شوند. جدول outbox و metadata نسخه/منبع قیمت و model-call records در استیج لازم افزوده می‌شوند.

قیمت/مقدار/fee/P&L با NUMERIC/Decimal و precision کافی بر اساس بازار؛ UTC برای ذخیره و timezone کاربر برای نمایش و bucketing گزارش. نرخ تبدیل fee و ارزش دارایی باید timestamp و مبنا داشته باشد؛ نرخ نامعلوم صفر فرض نشود.

FKها، indexهای بخش ۴۳، check مثبت‌بودن مقادیر، درصدها و uniqueness هدف شماره‌دار در هر signal/trade لازم‌اند. `exchange_markets(exchange_id,symbol,market_type)` یکتا؛ client/exchange order و fill IDs با account scope یکتا؛ idempotency با `user_id+operation+key` و request hash؛ external message با account+peer+message و revision scope. checksum تنها و در کل سامانه نباید پیام کاربران یا منابع مختلف را اشتباهاً ادغام کند.

trade_events و audit افزایشی‌اند؛ اصلاح با رویداد جدید. raw signal اصل متن و revisions را حفظ می‌کند. snapshot trade مستقل از تغییر signal و user defaults است. تراکنش DB ارسال خارجی را اتمی نمی‌کند: order intent/outbox قبل submit ذخیره، نتیجه خارجی با client_order_id بازیابی و سپس state اصلاح شود. Redis lock به‌تنهایی کافی نیست؛ DB uniqueness/row locks و version checks تصمیم مالی را حفاظت می‌کنند.

## Entry، مبلغ و Parser

ورودی کاربر «مبلغ سرمایه» مانند ۵۰ USDT است، نه حجم نهایی position. Engine با fees، leverage مجاز، balance، min notional و lot step مقدار را محاسبه می‌کند. مبنای amount در Margin، سرمایه/وثیقه اختصاص‌یافته است؛ notional و borrowing در preview جدا نمایش داده شوند.

یک Entry و حداکثر سه TP اجرایی. تمام متن و targets اضافی در raw/extraction metadata حفظ شوند. Entry Range به‌عنوان range و rule/version حفظ شود؛ پیش‌فرض preview می‌تواند midpoint نشان دهد ولی ابهام نیاز به تأیید دارد. Full-Auto فقط با rule صریح از پیش‌ذخیره‌شده منبع می‌تواند range را تبدیل کند. هیچ endpoint معامله مقدار مبهم را حدس نزند.

برای TPهای کمتر از سه، به‌طور پیش‌فرض سهم هدف‌های حذف‌شده به آخرین هدف موجود منتقل شود: یک هدف ۱۰۰٪، دو هدف ۱۰٪/۹۰٪؛ برای سه هدف ۱۰٪/۱۰٪/۸۰٪. کاربر درصد معتبر دیگری می‌تواند انتخاب کند. policy باید در preview و snapshot دیده شود.

confidence اطمینان فنی استخراج است؛ احتمال سود، تأیید منبع یا توصیه سرمایه‌گذاری نیست. missing SL/entry، چند pair یا تعارض direction، صرف‌نظر از score، مانع Full-Auto و نیازمند review هستند.

## Trailing و تقدم خروج

دو toggle جدا: step trailing برای حرکت SL به Entry/هدف قبلی، و Percentage Trailing برای stop با فاصله درصدی از بهترین قیمت بعد activation. در Smart Paste هر دو ON؛ Percentage trigger=TP1 و distance=۱٪. پس از activation، Percentage تقدم دارد و effective stop هرگز ضعیف‌تر نشود.

طبق ترجیح کاربر «با Percentage فقط trailing exits»، وقتی Percentage از ابتدای plan روشن است TPها سطح فعال‌سازی/نمایش‌اند و TP sell سفارش‌گذاری نمی‌شود؛ Initial SL تا activation برقرار است. وقتی روی معامله دارای TPهای موجود روشن/فعال می‌شود، TPهای باز cancel و fills واقعی reconcile می‌شوند؛ cancellation فرضی ممنوع و فروش مضاعف ناممکن باشد. وضعیت بدون پوشش حفاظتی به کاربر آشکار و مانع live جدید باشد.

Long stop = highest_after_activation × (۱−distance)، Short stop = lowest_after_activation × (۱+distance). عبور از TP3 باعث close صرفاً بر مبنای TP3 نمی‌شود. crash/restart high/low و stop را از DB بازیابی می‌کند. TP/SL، cancel/fill و manual close race باید به مقدار باقی‌مانده و وضعیت واقعی exchange محدود شوند.

## Telethon و تحلیل کانال — فقط S21

رابط source و Inbox پیش‌تر آماده می‌شود؛ پیاده‌سازی اتصال، session و listener فقط در آخرین استیج است. خواندن کانال محدود به دسترسی مجاز حساب انتخاب‌شده است. Telethon account client با Bot API یکسان فرض نشود. FloodWait، reconnect، catch-up bounded، edit/delete و dedup باید در adapter منبع رعایت شوند.

برای هر کانال روش Template، AI یا Hybrid انتخاب می‌شود. template profile قابل آزمون روی sample؛ AI با provider/model قابل تنظیم و خروجی schema-validated. متن کانال داده غیرقابل اعتماد است؛ اجازه تغییر policy، فراخوانی ابزار، دسترسی secrets یا اجرای سفارش نمی‌دهد. اسرار صرافی و Telethon هرگز به provider مدل فرستاده نشوند. متن نامعتبر/AI timeout/invalid schema نیازمند review است.

تحلیل کانال شامل قالب پیام، پوشش استخراج، ابهام، duplicate، کیفیت روی sample برچسب‌خورده و آمار سیگنال است. channel win rate یا بازده فقط با تاریخچه قیمت/fill معتبر و روش ارزیابی تعریف‌شده قابل گزارش است؛ از متن سیگنال به‌تنهایی محاسبه نشود. AI score بدون ارزیابی، calibrated confidence نامیده نشود.

Mode هر منبع Manual/Semi-Auto/Full-Auto است. Full-Auto پیش‌فرض خاموش و Paper پیش‌فرض است؛ rules منبع شامل amount، market، exchange، limits و parser validation‌اند. استیج ساخت کد مجوز سفارش واقعی با سرمایه کاربر نیست. فعال‌سازی عملی live باید در محصول با حساب مجاز، keys معتبر و انتخاب صریح انجام شود.

## شرط پذیرش واقعی

شبیه‌ساز، sandbox و live نتایج جدا دارند. نبود sandbox رسمی یا credentials باید شفاف باشد. هیچ معیار performance، اتصال واقعی یا استقرار روی هاست بدون شواهد انجام‌شده گزارش نشود. نسخه پایه در S20 با Manual/Smart Paste پذیرفته می‌شود؛ پذیرش Telethon و AI در آخر S21-W05 انجام می‌شود.
