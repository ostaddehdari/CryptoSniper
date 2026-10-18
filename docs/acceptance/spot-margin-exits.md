# پذیرش Spot/Margin و خروج‌ها — Stage20

| سناریو | وضعیت نسخه پایه |
|---|---|
| Paper Spot Long | مجاز؛ موتور مشترک و Simulator |
| Paper Spot Short | مسدود؛ Spot بدهی/Short ندارد |
| Paper Margin Long/Short | مجاز در Simulator؛ borrow/interest/repay دفتر شبیه‌ساز |
| Futures/Perpetual | غیرفعال |
| Binance sandbox/live write | غیرفعال و بررسی‌نشده |

سه هدف به‌طور پیش‌فرض سهم دقیق ۱۰٪، ۱۰٪ و ۸۰٪ دارند؛ گردکردن lot و dust در هدف آخر جمع می‌شود. Step Trailing پس از TP1 حد را به Entry و پس از TP2 به TP1 می‌برد. SL بر TP تقدم دارد و مجموع Fill خروج هرگز از Position بیشتر نمی‌شود.

با Percentage Trailing، رسیدن به trigger مالکیت خروج را به trailing می‌دهد و TPهای باقیمانده فروش انجام نمی‌دهند. قیمت می‌تواند از TP3 عبور کند، high/low-water به‌صورت monotonic ثبت شود و فقط reversal معتبر Position را یک‌بار ببندد. تغییر حالت با لغو نامعلوم fail-closed است و reconciliation لازم دارد.
