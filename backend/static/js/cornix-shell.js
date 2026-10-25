(() => {
  "use strict";
  const root = document.querySelector("[data-cornix-shell]");
  if (!root) return;

  const apiRoot = (root.dataset.apiRoot || "/").replace(/\/$/, "");
  const path = (value) => apiRoot + (value.startsWith("/") ? value : "/" + value);
  const usd = document.querySelector("[data-shell-usdt-usd]");
  const toman = document.querySelector("[data-shell-usdt-toman]");
  const clock = document.querySelector("[data-shell-live-time]");
  let inFlight = false;
  let lastFetch = 0;

  const fmt = (value) => {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value);
    return new Intl.NumberFormat("en-US", { maximumFractionDigits: 8 }).format(number);
  };

  async function refreshTicker(force = false) {
    const now = Date.now();
    if (clock) {
      clock.textContent = new Date().toLocaleTimeString("fa-IR", {
        hour: "2-digit", minute: "2-digit", second: "2-digit"
      });
    }
    if (!force && (inFlight || now - lastFetch < 15000)) return;
    inFlight = true;
    lastFetch = now;
    try {
      const response = await fetch(path("/api/v1/markets/header-ticker/"), {
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" }
      });
      if (!response.ok) return;
      const payload = await response.json();
      if (usd) usd.textContent = fmt(payload.usdt_usd);
      if (toman) toman.textContent = fmt(payload.usdt_toman);
    } catch (_) {
      // Shell remains usable if public price references are temporarily unavailable.
    } finally {
      inFlight = false;
    }
  }

  refreshTicker(true);
  setInterval(() => refreshTicker(false), 5000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshTicker(true);
  });
})();
