# پذیرش Manual و Smart Paste — Stage20

این مسیرها برای کاربر عادی و از رابط وب هستند؛ هیچ دستور shell برای ساخت یا بستن معامله لازم نیست.

## Manual

۱. ورود، افزودن حساب «شبیه‌ساز CryptoSniper» و رفتن به «ورود دستی معامله».
۲. انتخاب حساب/بازار، ثبت amount، Entry، حداکثر سه TP و یک SL و مشاهده preview.
۳. تثبیت Snapshot و تأیید صریح اجرای Paper.
۴. مشاهده Position و timeline؛ در محیط Paper فعال‌کردن سناریوی قیمت و ارسال Tick.
۵. مشاهده بسته‌شدن، Fill خروج، history و report.

## Smart Paste

۱. چسباندن متن در Smart Paste و مشاهده متن اصلی در کنار parse پیشنهادی.
۲. انتخاب account/market، اصلاح Entry/TP/SL، ثبت دلیل و تأیید دستی سیگنال.
۳. ساخت Trade Plan، preview، تثبیت و اجرای Paper.
۴. ادامه مستقل Worker تا Position و خروج؛ مرورگر می‌تواند بسته شود.
۵. مشاهده Alert/Notification، تاریخچه، P/L و Fee در Reports.

## مرز پذیرش

دو مسیر در CI مرورگر و موتور مشترک تا وضعیت `closed` بررسی می‌شوند. این پذیرش Simulator Paper است؛ مدرک Binance sandbox/live نیست. Telegram و AI در این نسخه ورودی پذیرش نیستند و تا S21 معوق‌اند.
