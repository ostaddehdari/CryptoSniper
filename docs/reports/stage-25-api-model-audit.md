# ممیزی مسیرهای API و مدل داده — S25-W01-T02

بازبینی UTC: 2026-11-26T18:29:19.019Z  
مبنای کد: [`764af56b499e086073cfbc8df7f9aaf623887682`](https://github.com/ostaddehdari/CryptoSniper/commit/764af56b499e086073cfbc8df7f9aaf623887682)  
قرارداد هدف: `projects/cryptosniper/proposal.json`، بخش `api_contracts` و `data_entities` در deployment-center، بازنگری ۲. مسیرهای پیشنهادی پروپوزال ادعای وجود در کد فعلی نیستند. این ممیزی فقط خواندن کد و migration است؛ اجرای API، پایگاه داده یا سرور انجام نشده است.

## ماتریس API

مبنای مسیرهای موجود [urls.py](https://github.com/ostaddehdari/CryptoSniper/blob/764af56b499e086073cfbc8df7f9aaf623887682/backend/config/urls.py#L1) است؛ method از decorator در view بررسی شد. مسیرها در URLConf نسبت به root Django نوشته شده‌اند و پیشوند reverse proxy محیط استقرار در این ممیزی تأیید نشده است.

| عملیات هدف پروپوزال | وضعیت و مسیر موجود در کد | اختلاف و تصمیم |
|---|---|---|
| `POST /signals/parse` بدون معامله | `POST api/v1/smart-paste/` در [views.py](https://github.com/ostaddehdari/CryptoSniper/blob/764af56b499e086073cfbc8df7f9aaf623887682/backend/apps/signals/views.py#L719) پیام را دریافت، Signal را ذخیره و برای review parse می‌کند. | **معادل خالص نیست**: parse هدف بدون side effect ذخیره‌سازی است؛ فعلاً قرارداد موجود را حفظ و API pure parse را در تغییر جدا طراحی کنید. |
| `GET /signals?status=&cursor=&limit=` | `GET api/v1/inbox/` در [views.py](https://github.com/ostaddehdari/CryptoSniper/blob/764af56b499e086073cfbc8df7f9aaf623887682/backend/apps/signals/views.py#L636)، فیلتر و برش ۱۰۰تایی دارد. | cursor/next_cursor قرارداد هدف در پاسخ دیده نشد؛ pagination و مالکیت در تسک Inbox بررسی و نسخه‌بندی شود. |
| `POST /trade-plans/preview` | `POST api/v1/manual/plans/` در [views.py](https://github.com/ostaddehdari/CryptoSniper/blob/764af56b499e086073cfbc8df7f9aaf623887682/backend/apps/tradeplans/views.py#L194) draft و preview را ذخیره می‌کند؛ `GET api/v1/manual/plans/<pk>/` و `POST .../confirm/` نیز هستند. | **هم‌نام یا بی‌اثر نیست**؛ preview محاسباتی بدون persistence باید به‌صورت endpoint مستقل یا قرارداد فعلی مستند شود. |
| `POST /trades` با Idempotency-Key و پاسخ 202 | `POST api/v1/paper/trades/` در [views.py](https://github.com/ostaddehdari/CryptoSniper/blob/764af56b499e086073cfbc8df7f9aaf623887682/backend/apps/trading/views.py#L118) با `plan_id` و `request_key` Paper را queue می‌کند؛ کد 201/200. `api/v1/trades/` در [api_stage24.py](https://github.com/ostaddehdari/CryptoSniper/blob/764af56b499e086073cfbc8df7f9aaf623887682/backend/apps/portfolio/api_stage24.py#L178) فقط GET است. | Alias بدون تفکیک Paper/Live نسازید؛ header، 409 و schema خطای هدف با قرارداد فعلی فرق دارد. |
| `POST /trades/{id}/actions` | endpoint واحد وجود ندارد؛ `api/v1/paper/<pk>/stop/`، `.../tick/` و `.../trailing/` و مسیرهای HTML close/cancel، به‌علاوه `external/<pk>/manage/` وجود دارند. | پیش از API مشترک، version/مالکیت/idempotency هر action و گونه trade را یکسان‌سازی کنید؛ adoption را با Paper action یکی نگیرید. |
| `GET /trades/{id}` و `GET /trades` با cursor | `GET api/v1/trades/` فهرست Paper/Live/External را با سقف داخلی می‌دهد؛ جزئیات JSON `GET api/v1/paper/trades/<pk>/` تنها Paper است. | جزئیات یکپارچه و cursor/next_cursor هدف هنوز قرارداد موجود نیست؛ نوع رکورد را در response حفظ کنید. |
| `POST /exchange-accounts/{id}/refresh` | `POST exchanges/<pk>/sync/` مسیر HTML/queue است؛ `POST api/v1/trades/refresh/` در [api_stage24.py](https://github.com/ostaddehdari/CryptoSniper/blob/764af56b499e086073cfbc8df7f9aaf623887682/backend/apps/portfolio/api_stage24.py#L256) همگام‌سازی read-only حساب‌های قابل استفاده مالک را انجام می‌دهد. | endpoint API تک‌حساب با job_id هدف نیست؛ refresh یکپارچه را اجرای سفارش تعبیر نکنید. |
| `POST /telegram/sources/{id}/imports` | در URLConf مسیر متناظر دیده نشد؛ تنظیمات Telegram و listener/backfill در کد وجود دارد. | API درخواست import با cursor/job_id نیازمند طراحی جداست؛ نبود route به معنی نبود همه قابلیت‌های import نیست. |
| `GET /health/live` و `GET /health/ready` | `health/live/` و `health/ready/` در [urls.py](https://github.com/ostaddehdari/CryptoSniper/blob/764af56b499e086073cfbc8df7f9aaf623887682/backend/config/urls.py#L274)؛ ready بر اساس dependency_status، 200/503. | مسیرهای root Django موجودند؛ public prefix و policy افشای جزئیات با پیکربندی استقرار جدا بررسی شود. |

## ماتریس مدل و migration

| هدف داده پروپوزال | موجود در مدل/نسخه migration | شکاف یا قاعده پذیرش |
|---|---|---|
| User/Settings و ExchangeAccount/Market | `UserExchangeAccount` دارای owner، environment، permission، credential رمزنگاری‌شده و UNIQUE(owner,exchange,label) است؛ `BalanceSnapshot` قید nonnegative دارد ([models.py](https://github.com/ostaddehdari/CryptoSniper/blob/764af56b499e086073cfbc8df7f9aaf623887682/backend/apps/exchanges/models.py#L123)). | قرارداد هدف `email/password_hash/Settings` را نباید به مدل فعلی Django تحمیل کرد؛ تطبیق هویت و retention مستقل بررسی شود. |
| SignalSource/RawSignal/Signal | مدل‌های سیگنال و revision/Telegram در [models.py](https://github.com/ostaddehdari/CryptoSniper/blob/764af56b499e086073cfbc8df7f9aaf623887682/backend/apps/signals/models.py#L1) و migrationهای 0002–0010 موجودند. | قید dedup را با scope واقعی account/channel/message/revision و داده migrated در DATA-001 بازبینی کنید. |
| Trade/Target/TrailingRule | `TradePlan` دارای owner، Decimal، token یکتا، preview و `approved_snapshot` است ([models.py](https://github.com/ostaddehdari/CryptoSniper/blob/764af56b499e086073cfbc8df7f9aaf623887682/backend/apps/tradeplans/models.py#L10)). `Trade` و `TradeTarget` و `TradeProtection` Paper در [models.py](https://github.com/ostaddehdari/CryptoSniper/blob/764af56b499e086073cfbc8df7f9aaf623887682/backend/apps/trading/models.py#L11) هستند. Migrationهای `tradeplans/0003` و `trading/0007` trigger هدف را ثبت کرده‌اند. | مجموع سهم TP=۱۰۰٪ در service/preview سنجیده می‌شود، نه یک constraint سطری DB؛ immutable بودن snapshot پس از تأیید باید در مسیرهای نوشتن و تست بررسی شود. `TradeProtection` native stop نیست. |
| Order/Fill/Position | `Order` دارای UNIQUE(account,client_order_id)، `OrderFill` دارای UNIQUE(account,exchange_fill_id) و `Position` یک‌به‌یک با Trade است ([models.py](https://github.com/ostaddehdari/CryptoSniper/blob/764af56b499e086073cfbc8df7f9aaf623887682/backend/apps/trading/models.py#L70)). | این ledger برای Paper است؛ `LiveSpotOrder` مدل مجزا با owner/account/market و کلید درخواست و سفارش یکتا دارد ([models.py](https://github.com/ostaddehdari/CryptoSniper/blob/764af56b499e086073cfbc8df7f9aaf623887682/backend/apps/exchanges/models.py#L223)، migration `exchanges/0006`). Filled order به‌تنهایی position قابل مدیریت نیست. |
| Intent/Outbox/Idempotency | `Trade` دارای UNIQUE(owner,request_key)، request_hash و snapshot؛ `ExecutionOutbox` یک‌به‌یک با Order و حالت uncertain/fence دارد ([models.py](https://github.com/ostaddehdari/CryptoSniper/blob/764af56b499e086073cfbc8df7f9aaf623887682/backend/apps/trading/models.py#L205)؛ migration `trading/0003`). `TradeAction` دارای UNIQUE(trade,request_key) و migration `trading/0004` است. | مدل عمومی `UNIQUE(owner,operation,key)` و outbox واحد Live/Paper عیناً وجود ندارد؛ تغییر باید بدون شکستن idempotency موجود و با migration آزموده طراحی شود. |
| External observation/adoption | `ExternalObservation` دارای UNIQUE(account,kind,external_id) و سیاست `ExternalTradePolicy` یک‌به‌یک، با حجم تأییدشده و trailing است ([models.py](https://github.com/ostaddehdari/CryptoSniper/blob/764af56b499e086073cfbc8df7f9aaf623887682/backend/apps/operations/models.py#L50)، migration `operations/0002`). | observation صرفاً مشاهده است؛ مدیریت و trailing واقعی فقط پس از adoption و reconciliation معتبر. |
| Event/Audit/Alert/Report | `TradeEvent` append-oriented با trade/payload/time در [models.py](https://github.com/ostaddehdari/CryptoSniper/blob/764af56b499e086073cfbc8df7f9aaf623887682/backend/apps/trading/models.py#L227)؛ گزارش و audit در ماژول‌های جدا موجودند. | حذف cascade، retention، scope مالک و rebuild گزارش با آزمون مستقل DATA-001/DATA-003 سنجیده شود؛ صرف وجود مدل، تضمین append-only نیست. |

## ADR-25-02 — حفظ قرارداد موجود و مهاجرت تدریجی

**وضعیت:** تصمیم پیشنهادی برای تسک‌های اجرا؛ هنوز API یا schema تغییر نکرده است.

1. APIهای موجود `/api/v1/manual/`، `/api/v1/paper/` و فهرست یکپارچه `/api/v1/trades/` را بدون تغییر ناگهانی حفظ کنید. برای قرارداد هدف پروپوزال، ابتدا schema نسخه‌دار، error envelope و تست سازگاری بسازید؛ سپس alias یا endpoint جدید با تفکیک روشن Paper/Live اضافه کنید. نام مشابه به‌تنهایی دلیل معادل‌بودن رفتار نیست.
2. `TradePlan.approved_snapshot` و Paper `Trade/Order/ExecutionOutbox` را منبع حقیقت چرخه Paper نگه دارید. `LiveSpotOrder` و `ExternalObservation/ExternalTradePolicy` را بدون تبدیل خودکار fill به position مدیریت کنید. هر مدل مشترک intent، outbox یا ledger بعدی باید migration، backfill، uniqueness و rollback آزموده داشته باشد.
3. مالکیت `owner/account` و زمان UTC در همه رکوردهای مالی و مرز transaction با تست DATA-001 اثبات شود. مسیرهای read-only dashboard/chart/refresh هرگز submit را فعال نکنند. Live gate پیش‌فرض خاموش و پذیرش هر provider در S29 مستقل بماند.

**پیامد:** UI و کلاینت فعلی دچار شکست ناگهانی نمی‌شوند؛ قرارداد نهایی پروپوزال و یکپارچه‌سازی Live تا تسک‌های بعدی و شواهد آزمون باز می‌ماند. این ADR به‌تنهایی مجوز migration یا اجرای سفارش واقعی نیست.

## کنترل بازبینی

- URLConf و decoratorهای viewهای routeهای بالا در همان SHA خوانده شدند.
- مدل‌های Trading، TradePlan، Exchange، Signal و Operations و migrationهای `trading/0001,0003,0004,0007`، `tradeplans/0001,0003`، `exchanges/0006`، `operations/0002` برای ادعاهای جدول تطبیق داده شدند.
- آزمون runtime، `makemigrations --check`، `migrate`، PostgreSQL، CI، provider و production اجرا نشده‌اند. S25-W02-T02 برای بررسی عملی schema/rollback و S25-W01-T03 برای تصمیم‌های باز باقی‌اند.
