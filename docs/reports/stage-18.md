# استیج ۱۸ — شبیه‌ساز کامل و اعتبارسنجی Paper | 0.18.0rc1

شبیه‌ساز Stage03 اکنون مسیر قیمت seedدار، زمان مجازی، partial fill، rejection، rate limit و قواعد lot/min-notional دارد. همان risk/state/executor/exits و ledger برای Paper Spot و Margin استفاده می‌شود و مرز مرکزی هر حساب یا Adapter غیر Simulator را پیش از انتخاب transport رد می‌کند.

| ورک | نتیجه |
|---|---|
| S18-W01 | مسیر قیمت و order ID قطعی با seed؛ partial fill، latency مجازی، rejection و rate limit قابل بازتولید؛ fee/min order همان metadata بازار. |
| S18-W02 | مرز `require_paper_simulator` در executor و provider؛ credential باطل، حساب Live، adapter واقعی یا build غیر Paper fail-closed می‌شود. |
| S18-W03 | Margin Long/Short با borrow ledger، بهره Decimal، repay و finance event؛ TP/SL/trailing دوطرفه، تسویه بدون dust و جداسازی دو معامله همزمان. |
| S18-W04 | failure injection قبل/بعد submit، receipt پایدار، fencing، restart/recovery، duplicate و cancel/fill race؛ unknown تنها پس از lookup authoritative قابل retry است. |
| S18-W05 | API/UI ماتریس readiness و محدودیت adapter؛ مسیر Manual و Smart Paste تا executor مشترک و اتصال alerts/reports آزموده شد. |

## وضعیت Adapter و mode

| مسیر | وضعیت |
|---|---|
| Simulator Spot Long | پیاده‌سازی و CI یکپارچه پاس |
| Simulator Margin Long/Short | پیاده‌سازی و CI یکپارچه پاس؛ debt واقعی نیست |
| Binance read | پیاده‌سازی قبلی، بدون تأیید حساب واقعی |
| Binance sandbox/live write | غیرفعال و بررسی‌نشده |
| Telegram/channel/AI | طبق برنامه تا S21 معوق |

[CI منبع دقیق](https://github.com/ostaddehdari/CryptoSniper/actions/runs/39107786569) روی commit `0230456ada42d6309cf5c2d4ace9e433e979f9c2` با ۱۹۴ تست، PostgreSQL 16، Redis 7، صف‌های مستقل Worker/Beat و Chromium پاس شد. داشبورد ۱۷ query و ۲۷٫۲۱ms زمان build داشت و artifact شواهد `12128808194` است. نتیجه Simulator شاهد sandbox/live یا سودآوری نیست. نصب Stage18 روی VPS و پذیرش مرورگر عمومی نیز پس از بسته تأییدشده باقی می‌ماند.
