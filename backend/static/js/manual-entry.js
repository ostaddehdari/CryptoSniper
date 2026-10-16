/* Owner-specific display hints. The server always recomputes plans via Decimal. */
(() => {
  "use strict";
  const root = document.querySelector("[data-manual-context-url]");
  if (!root) return;
  const account = root.querySelector("[name=account]");
  const market = root.querySelector("[name=market]");
  const entry = root.querySelector("[name=entry_price]");
  const hint = root.querySelector("[data-manual-hint]");
  const options = [...market.options].map(x => ({value:x.value, text:x.text, exchange:x.dataset.exchange}));
  function updateMarkets() {
    const selected = account.selectedOptions[0];
    const exchange = selected?.dataset.exchange || "";
    const current = market.value;
    market.replaceChildren();
    for (const item of options) {
      if (!item.value || item.exchange === exchange) {
        const option = new Option(item.text, item.value);
        option.dataset.exchange = item.exchange;
        market.add(option);
      }
    }
    if (Array.from(market.options).some(x => x.value === current)) market.value = current;
  }
  let seq=0;
  async function refresh() {
    const n=++seq;
    if (!account.value || !market.value) { hint.textContent="ابتدا حساب و بازار را انتخاب کنید."; return; }
    const p=new URLSearchParams({account:account.value, market:market.value, entry:entry.value});
    try {
      const res=await fetch(root.dataset.manualContextUrl+"?"+p,{credentials:"same-origin", cache:"no-store"});
      if(!res.ok)throw Error("unavailable");
      const data=await res.json();
      if (n!==seq)return;
      const price= data.quote?.price || "ناموجود";
      const age= data.price_stale ? " (قدیمی/غیرقابل اتکا)" : " (به‌روز)";
      const balance= data.balance ? data.balance.free+" "+data.balance.asset : "موجودی همگام نشده";
      const diff= data.distances?.price_to_entry_percent;
      hint.textContent="قیمت نمایشی: "+price+age+" | موجودی آزاد: "+balance+
          " | سقف اهرم: "+data.market.max_leverage+
          (diff === undefined ? "" : " | فاصله با Entry: "+Number(diff).toFixed(2)+"%");
    } catch (_e) {if(n===seq)hint.textContent="اتصال قیمت در دسترس نیست؛ آخرین اطلاعات معتبر را بررسی کنید.";}
  }
  account.addEventListener("change",()=>{updateMarkets();void refresh();});
  market.addEventListener("change",()=>void refresh());
  entry.addEventListener("input",()=>void refresh());
  updateMarkets();void refresh();
})();
