/* Stage 04: bounded user-scoped quote updates; no trade or external requests. */
(() => {
  "use strict";
  const table = document.querySelector("#market-watchlist");
  if (!table) return;
  const rows = [...table.querySelectorAll("tr[data-market-id]")];
  if (!rows.length) return;
  const ids = rows.map(row => row.dataset.marketId).filter(id => /^\d+$/.test(id)).slice(0, 20);
  if (!ids.length) return;
  const url = table.dataset.quotesUrl + "?" + ids.map(id => "market=" + encodeURIComponent(id)).join("&");
  let delay = 15000;
  let stopped = false;
  const apply = item => {
    const row = rows.find(row => row.dataset.marketId === String(item.market_id));
    if (!row) return;
    const price = row.querySelector(".quote-price");
    const state = row.querySelector(".quote-status");
    if (!price || !state) return;
    const quote = item.quote;
    price.textContent = quote ? quote.price : "—";
    state.textContent = !quote ? "ناموجود" : quote.stale ? "قدیمی" : "تازه";
    state.classList.toggle("is-stale", !!quote?.stale);
    state.classList.toggle("is-unavailable", !quote);
  };
  async function poll() {
    if (stopped || document.hidden) return;
    try {
      const response = await fetch(url, {credentials: "same-origin", cache: "no-store",
        headers: {"Accept": "application/json"}});
      if (!response.ok) throw new Error("feed status");
      const payload = await response.json();
      if (!Array.isArray(payload.markets)) throw new Error("invalid feed");
      payload.markets.forEach(apply);
      delay = 15000;
    } catch (_error) {
      rows.forEach(row => {
        const state = row.querySelector(".quote-status");
        if (state) { state.textContent = "ارتباط قطع است"; state.classList.add("is-stale"); }
      });
      delay = Math.min(delay * 2, 60000);
    }
  }
  async function loop() {
    await poll();
    if (!stopped) window.setTimeout(loop, delay);
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) void poll(); });
  window.addEventListener("pagehide", () => { stopped = true; }, {once: true});
  void loop();
})();
