(() => {
  "use strict";
  const root = document.querySelector("[data-manual-context-url]");
  if (!root) return;
  const account = root.querySelector("[name=account]");
  const market = root.querySelector("[name=market]");
  const search = root.querySelector("[data-market-search]");
  const results = root.querySelector("[data-market-results]");
  const hint = root.querySelector("[data-manual-hint]");
  if (!account || !market) return;

  const options = [...market.options].filter(o => o.value).map(o => ({
    value: o.value, text: o.textContent.trim(), exchange: o.dataset.exchange || ""
  }));
  const exchangeId = () => account.selectedOptions[0]?.dataset.exchange || "";
  const eligible = () => options.filter(o => !exchangeId() || o.exchange === exchangeId());

  function renderResults() {
    if (!search || !results) return;
    const query = search.value.trim().toLowerCase();
    results.replaceChildren();
    if (!query) { results.hidden = true; return; }
    const matches = eligible().filter(o => o.text.toLowerCase().includes(query)).slice(0, 12);
    for (const item of matches) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button button-soft button-full";
      button.style.marginTop = "6px";
      button.textContent = item.text;
      button.addEventListener("click", () => {
        market.value = item.value;
        search.value = item.text;
        results.hidden = true;
        market.dispatchEvent(new Event("change", {bubbles:true}));
      });
      results.append(button);
    }
    if (!matches.length) results.textContent = "بازار قابل معامله‌ای پیدا نشد.";
    results.hidden = false;
  }

  function updateMarkets() {
    const current = market.value;
    const rows = eligible();
    market.replaceChildren(new Option("انتخاب بازار", ""));
    for (const item of rows) {
      const option = new Option(item.text, item.value);
      option.dataset.exchange = item.exchange;
      market.add(option);
    }
    market.value = rows.some(o => o.value === current) ? current : "";
    if (!market.value && search) search.value = "";
    renderResults();
  }

  async function refresh() {
    if (!account.value || !market.value) {
      hint.textContent = "ابتدا حساب و یک بازار قابل معامله را انتخاب کنید.";
      return;
    }
    hint.textContent = "در حال دریافت قیمت و محدودیت‌های بازار…";
    try {
      const url = new URL(root.dataset.manualContextUrl, window.location.origin);
      url.searchParams.set("account", account.value);
      url.searchParams.set("market", market.value);
      const response = await fetch(url, {headers: {"Accept":"application/json"}});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "context_failed");
      hint.textContent = `قیمت فعلی: ${data.price ?? "—"} · موجودی آزاد: ${data.free_balance ?? "—"} ${data.quote_asset ?? ""} · سقف اهرم: ${data.max_leverage ?? "—"}×`;
    } catch (_) {
      hint.textContent = "دریافت اطلاعات بازار ناموفق بود؛ اتصال و همگام‌سازی حساب را بررسی کنید.";
    }
  }

  account.addEventListener("change", () => { updateMarkets(); refresh(); });
  market.addEventListener("change", () => {
    const selected = market.selectedOptions[0];
    if (search && selected?.value) search.value = selected.textContent.trim();
    refresh();
  });
  search?.addEventListener("input", renderResults);
  search?.addEventListener("focus", renderResults);
  document.addEventListener("click", e => {
    if (results && search && !results.contains(e.target) && e.target !== search) results.hidden = true;
  });

  updateMarkets();
  const selected = market.selectedOptions[0];
  if (search && selected?.value) search.value = selected.textContent.trim();
  refresh();
})();