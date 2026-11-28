(() => {
  "use strict";
  const root = document.querySelector("[data-manual-context-url]");
  if (!root) return;
  // Drop legacy unsaved values from this history entry before another user can see them.
  const oldDraftKey = `form:${window.location.pathname}`;
  if (window.history.state && Object.prototype.hasOwnProperty.call(window.history.state, oldDraftKey)) {
    const safeState = {...window.history.state};
    delete safeState[oldDraftKey];
    window.history.replaceState(safeState, "");
  }
  const account = root.querySelector("[name=account]");
  const market = root.querySelector("[name=market]");
  const search = root.querySelector("[data-market-search]");
  const results = root.querySelector("[data-market-results]");
  const hint = root.querySelector("[data-manual-hint]");
  const entry = root.querySelector("[name=entry_price]");
  const mode = root.querySelector("[name=entry_mode]");
  const form = root.querySelector("#manual-entry-form");
  const trailing = root.querySelector("[name=percentage_trailing]");
  const trigger = root.querySelector("[name=trailing_trigger]");
  const trailingDistance = root.querySelector("[name=trailing_distance]");
  if (!account || !market) return;

  const options = [...market.options].filter(o => o.value).map(o => ({
    value: o.value, text: o.textContent.trim(), exchange: o.dataset.exchange || ""
  }));
  const exchangeId = () => account.selectedOptions[0]?.dataset.exchange || "";
  const eligible = () => options.filter(o => !exchangeId() || o.exchange === exchangeId());

  function showDistances() {
    const base = Number(entry?.value);
    const side = form?.elements.namedItem("side")?.value || "long";
    for (const name of ["tp1", "tp2", "tp3"]) {
      const output = root.querySelector(`[data-tp-distance="${name}"]`);
      const price = Number(form?.elements.namedItem(name)?.value);
      if (!output) continue;
      if (!base || !Number.isFinite(base) || !price || !Number.isFinite(price)) {
        output.textContent = "فاصله از ورود: —";
      } else {
        const distance = (price - base) / base * 100 * (side === "short" ? -1 : 1);
        output.textContent = `فاصله از ورود: ${new Intl.NumberFormat("fa-IR", {maximumFractionDigits: 3}).format(distance)}٪${distance <= 0 ? " · سمت سود را بررسی کنید" : ""}`;
      }
    }
  }

  function updateTrailing() {
    if (trigger) trigger.disabled = !trailing?.checked;
    if (trailingDistance) trailingDistance.readOnly = !trailing?.checked;
    const note = root.querySelector("[data-trailing-hint]");
    if (note) note.textContent = trailing?.checked ? "Trailing TP پس از هدف انتخاب‌شده فعال می‌شود." : "Trailing TP خاموش است؛ هدف‌ها مطابق سهم تعیین‌شده باقی می‌مانند.";
  }

  function updateMode() {
    const note = root.querySelector("[data-entry-mode-hint]");
    if (note) note.textContent = mode?.value === "market"
      ? "Market: قیمت ورود، برآوردی از قیمت تازه بازار است؛ ارسال سفارش واقعی انجام نمی‌شود."
      : "Limit: قیمت ورود مشخص را وارد کنید؛ این فرم ابتدا پیش‌نویس می‌سازد.";
    if (entry) entry.readOnly = mode?.value === "market";
    if (mode?.value === "market") refresh();
  }

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
      const price = data.quote && !data.price_stale ? data.quote.price : "ناموجود یا قدیمی";
      if (mode?.value === "market" && entry) entry.value = data.quote && !data.price_stale ? data.quote.price : "";
      const balance = data.balance?.free ?? "—";
      hint.textContent = `قیمت فعلی: ${price} · موجودی آزاد: ${balance} ${data.balance?.asset ?? ""} · سقف اهرم: ${data.market?.max_leverage ?? "—"}×`;
      showDistances();
    } catch (_) {
      hint.textContent = "دریافت اطلاعات بازار ناموفق بود؛ اتصال و همگام‌سازی حساب را بررسی کنید.";
    }
  }

  account.addEventListener("change", () => {
    if (entry) entry.value = "";
    updateMarkets();
    refresh();
  });
  market.addEventListener("change", () => {
    if (entry) entry.value = "";
    const selected = market.selectedOptions[0];
    if (search && selected?.value) search.value = selected.textContent.trim();
    refresh();
  });
  search?.addEventListener("input", renderResults);
  search?.addEventListener("focus", renderResults);
  form?.addEventListener("input", showDistances);
  form?.addEventListener("change", showDistances);
  mode?.addEventListener("change", updateMode);
  trailing?.addEventListener("change", updateTrailing);
  document.addEventListener("click", e => {
    if (results && search && !results.contains(e.target) && e.target !== search) results.hidden = true;
  });

  updateMarkets();
  const selected = market.selectedOptions[0];
  if (search && selected?.value) search.value = selected.textContent.trim();
  refresh();
  showDistances();
  updateTrailing();
  updateMode();
})();
