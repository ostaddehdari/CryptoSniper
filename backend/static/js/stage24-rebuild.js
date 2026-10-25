(() => {
  "use strict";

  const root = document.querySelector("[data-stage24-root]");
  if (!root) return;

  const qs = (s, p = document) => p.querySelector(s);
  const qsa = (s, p = document) => Array.from(p.querySelectorAll(s));
  const appRoot = (root.dataset.apiRoot || "/").replace(/\/$/, "");
  const appPath = (path) => `${appRoot}${path.startsWith("/") ? path : "/" + path}`;
  const csrf = qs(".s24-csrf input[name=csrfmiddlewaretoken]")?.value || "";
  const state = {
    route: "overview",
    signalView: "active",
    signalLayout: "cards",
    signals: [],
    selectedSignal: null,
    selectedSignalDetail: null,
    tradeView: "active",
    trades: [],
    selectedTrade: null,
    market: null,
    interval: "5m",
    accounts: [],
    poller: null,
  };

  let tickerInFlight = false;
  let tickerLastAt = 0;

  const colors = {
    entry: "#2563eb",
    tp1: "#1fa86f",
    tp2: "#19a76f",
    tp3: "#10855a",
    tp: "#19a76f",
    sl: "#e05260",
    stop: "#e05260",
    expired: "#f59e0b",
    external: "#7c5ce7",
    default: "#64748b",
  };

  function esc(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;").replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function n(value, fallback = "—") {
    if (value === null || value === undefined || value === "") return fallback;
    const num = Number(value);
    if (!Number.isFinite(num)) return esc(value);
    return new Intl.NumberFormat("en-US", { maximumFractionDigits: 8 }).format(num);
  }

  function faDate(value) {
    if (!value) return "—";
    try {
      return new Intl.DateTimeFormat("fa-IR", {
        dateStyle: "short", timeStyle: "short"
      }).format(new Date(value));
    } catch (_) { return "—"; }
  }

  function toast(message, error = false) {
    const node = document.createElement("div");
    node.className = "s24-toast" + (error ? " error" : "");
    node.textContent = message;
    document.body.appendChild(node);
    setTimeout(() => node.remove(), 3600);
  }

  async function api(url, options = {}) {
    const headers = { Accept: "application/json", ...(options.headers || {}) };
    if (options.method && options.method !== "GET") {
      headers["X-CSRFToken"] = csrf;
      if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    }
    const response = await fetch(url, {
      credentials: "same-origin",
      cache: "no-store",
      ...options,
      headers,
    });
    let payload = {};
    try { payload = await response.json(); } catch (_) {}
    if (!response.ok) {
      const msg = payload.error || payload.detail || ("HTTP " + response.status);
      throw new Error(Array.isArray(msg) ? msg.join("؛ ") : String(msg));
    }
    return payload;
  }

  async function loadTicker(force = false) {
    const now = Date.now();
    const time = qs("[data-live-time]");
    if (time) time.textContent = new Date().toLocaleTimeString("fa-IR", {hour:"2-digit",minute:"2-digit",second:"2-digit"});
    if (!force && (tickerInFlight || now - tickerLastAt < 15000)) return;
    tickerInFlight = true;
    tickerLastAt = now;
    try {
      const payload = await api(appPath("/api/v1/markets/header-ticker/"));
      const usd = qs("[data-usdt-usd]"), toman = qs("[data-usdt-toman]");
      if (usd) usd.textContent = n(payload.usdt_usd);
      if (toman) toman.textContent = n(payload.usdt_toman);
    } catch (_) {
      // The workspace remains usable when a public reference feed is unavailable.
    } finally {
      tickerInFlight = false;
    }
  }

  async function loadAccounts() {
    if (state.accounts.length) return;
    const select = qs("[data-account-select]");
    if (!select) return;
    try {
      const payload = await api(appPath("/api/v1/exchanges/"));
      state.accounts = (payload.accounts || []).filter((a) => ["connected", "restricted"].includes(a.status));
      select.innerHTML = '<option value="">انتخاب حساب</option>' + state.accounts.map((a) =>
        `<option value="${a.id}" data-exchange="${esc(a.exchange)}">${esc(a.label)} · ${esc(a.exchange)}</option>`
      ).join("");
    } catch (error) {
      toast(error.message, true);
    }
  }

  async function loadOverview() {
    try {
      const payload = await api(appPath("/api/v1/dashboard/"));
      const openNode = qs("[data-overview-open]");
      const todayNode = qs("[data-overview-today]");
      const signalsNode = qs("[data-overview-signals]");
      const asofNode = qs("[data-overview-asof]");
      if (openNode) openNode.textContent = n(payload.open_trades, "0");
      if (todayNode) todayNode.textContent = n(payload.today_trades, "0");
      if (signalsNode) signalsNode.textContent = n(payload.active_signals, "0");
      if (asofNode) asofNode.textContent = "آخرین بروزرسانی: " + faDate(payload.as_of);
      const accounts = qs("[data-overview-accounts]");
      if (accounts) {
        const rows = payload.accounts || [];
        accounts.innerHTML = rows.length ? rows.map((row) => `<div class="s24-overview-account">
          <div><strong>حساب #${esc(row.id)}</strong><span>${esc(row.base_currency || "")}</span></div>
          <div><small>ارزش شناخته‌شده</small><b>${n(row.known_valuation)}</b></div>
          <div><small>قابل استفاده</small><b>${n(row.known_available_valuation)}</b></div>
        </div>`).join("") : '<div class="s24-empty-inline">حساب متصل برای نمایش وجود ندارد.</div>';
      }
    } catch (error) {
      const accounts = qs("[data-overview-accounts]");
      if (accounts) accounts.innerHTML = `<div class="s24-empty-inline">${esc(error.message)}</div>`;
    }
  }

  function setActive(group, attr, value) {
    qsa("button", group).forEach((button) => {
      button.classList.toggle("active", button.dataset[attr] === value);
    });
  }

  function route() {
    const value = (location.hash || "#/overview").replace(/^#\/?/, "").split("?")[0];
    state.route = ["overview", "inbox", "newtrade", "trades"].includes(value) ? value : "overview";
    qsa("[data-page]").forEach((page) => { page.hidden = page.dataset.page !== state.route; });
    qsa("[data-route-link]").forEach((link) => link.classList.toggle("active", link.dataset.routeLink === state.route));
    if (state.route === "overview") loadOverview();
    if (state.route === "inbox") loadSignals();
    if (state.route === "trades") loadTrades();
    if (state.route === "newtrade") { loadAccounts(); if (state.market) loadNewTradeChart(); }
    restartPolling();
  }

  function resizeCanvas(canvas) {
    const ratio = Math.max(1, window.devicePixelRatio || 1);
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(320, Math.floor(rect.width));
    const height = Math.max(220, Math.floor(rect.height));
    canvas.width = Math.floor(width * ratio);
    canvas.height = Math.floor(height * ratio);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    return { ctx, width, height };
  }

  function drawChart(canvas, payload, emptyNode) {
    if (!canvas) return;
    const candles = payload?.candles || [];
    if (!candles.length) {
      if (emptyNode) { emptyNode.hidden = false; emptyNode.textContent = "داده کندل برای این بازار در دسترس نیست."; }
      const { ctx, width, height } = resizeCanvas(canvas);
      ctx.clearRect(0, 0, width, height);
      return;
    }
    if (emptyNode) emptyNode.hidden = true;
    const { ctx, width, height } = resizeCanvas(canvas);
    ctx.clearRect(0, 0, width, height);

    const left = 16, right = 74, top = 18, bottom = 32;
    const cw = width - left - right, ch = height - top - bottom;
    const levels = payload.overlay?.levels || [];
    let min = Math.min(...candles.map((c) => c.low), ...levels.map((l) => Number(l.price)).filter(Number.isFinite));
    let max = Math.max(...candles.map((c) => c.high), ...levels.map((l) => Number(l.price)).filter(Number.isFinite));
    if (!(max > min)) { max += 1; min -= 1; }
    const pad = (max - min) * 0.08;
    min -= pad; max += pad;
    const y = (price) => top + (max - price) / (max - min) * ch;
    const x = (index) => left + (index + .5) / candles.length * cw;

    ctx.strokeStyle = "#edf1f6"; ctx.lineWidth = 1;
    ctx.font = "10px Arial"; ctx.fillStyle = "#8895a8";
    for (let i = 0; i <= 5; i++) {
      const yy = top + ch * i / 5;
      ctx.beginPath(); ctx.moveTo(left, yy); ctx.lineTo(left + cw, yy); ctx.stroke();
      const price = max - (max - min) * i / 5;
      ctx.fillText(n(price), left + cw + 7, yy + 3);
    }

    const step = Math.max(2, cw / candles.length);
    const bodyW = Math.max(2, Math.min(8, step * .62));
    candles.forEach((c, i) => {
      const xx = x(i);
      const up = c.close >= c.open;
      const color = up ? "#14a36f" : "#e05260";
      ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(xx, y(c.high)); ctx.lineTo(xx, y(c.low)); ctx.stroke();
      const yo = y(c.open), yc = y(c.close);
      ctx.fillRect(xx - bodyW / 2, Math.min(yo, yc), bodyW, Math.max(1.5, Math.abs(yo - yc)));
    });

    levels.forEach((level) => {
      const price = Number(level.price);
      if (!Number.isFinite(price)) return;
      const yy = y(price);
      const color = colors[level.kind] || (String(level.kind).startsWith("tp") ? colors.tp : colors.default);
      ctx.save();
      ctx.strokeStyle = color; ctx.globalAlpha = .8; ctx.setLineDash([6, 5]);
      ctx.beginPath(); ctx.moveTo(left, yy); ctx.lineTo(left + cw, yy); ctx.stroke();
      ctx.setLineDash([]); ctx.globalAlpha = 1; ctx.fillStyle = color;
      ctx.font = "700 10px Arial"; ctx.fillText(level.label || level.kind, left + cw + 7, yy - 5);
      ctx.restore();
    });

    const markers = payload.overlay?.markers || [];
    const times = candles.map((c) => Number(c.time));
    markers.forEach((marker) => {
      const mt = Number(marker.time);
      if (!Number.isFinite(mt)) return;
      let idx = 0, dist = Infinity;
      times.forEach((time, i) => {
        const d = Math.abs(time - mt);
        if (d < dist) { dist = d; idx = i; }
      });
      const xx = x(idx);
      const kind = String(marker.kind || "default");
      const level = levels.find((l) => l.kind === kind);
      const yy = level ? y(Number(level.price)) : y(candles[idx].close);
      const color = colors[kind] || (kind.startsWith("tp") ? colors.tp : colors.default);
      ctx.save();
      ctx.strokeStyle = color; ctx.globalAlpha = .55; ctx.setLineDash([3, 5]);
      ctx.beginPath(); ctx.moveTo(xx, top); ctx.lineTo(xx, top + ch); ctx.stroke();
      ctx.setLineDash([]); ctx.globalAlpha = 1;
      ctx.beginPath(); ctx.arc(xx, yy, 5.5, 0, Math.PI * 2); ctx.fillStyle = "#fff"; ctx.fill();
      ctx.lineWidth = 3; ctx.strokeStyle = color; ctx.stroke();
      ctx.fillStyle = color; ctx.font = "700 9px Arial"; ctx.fillText(marker.label || kind, Math.min(xx + 7, left + cw - 35), Math.max(top + 10, yy - 8));
      ctx.restore();
    });

    ctx.fillStyle = "#9aa6b7"; ctx.font = "9px Arial";
    const labelCount = Math.min(5, candles.length);
    for (let i = 0; i < labelCount; i++) {
      const idx = Math.floor(i * (candles.length - 1) / Math.max(1, labelCount - 1));
      const date = new Date(candles[idx].time * 1000);
      ctx.fillText(date.toLocaleTimeString("fa-IR", { hour: "2-digit", minute: "2-digit" }), x(idx) - 18, height - 10);
    }
  }

  async function chartFor(params, canvas, empty) {
    const query = new URLSearchParams(params);
    const payload = await api(appPath("/api/v1/markets/chart/?") + query.toString());
    drawChart(canvas, payload, empty);
    return payload;
  }

  function miniSignal(item) {
    const long = item.side !== "short";
    const path = long ? "M8 82 C35 98 48 20 82 72 S132 96 154 26 S205 16 224 38" : "M8 28 C35 12 48 90 82 38 S132 14 154 84 S205 92 224 62";
    const tps = (item.targets || []).slice(0, 3);
    return `<div class="s24-mini">
      <svg viewBox="0 0 232 108" aria-hidden="true">
        <path d="${path}" fill="none" stroke="#2f66e8" stroke-width="2"/>
        <line x1="8" y1="88" x2="224" y2="88" stroke="#ef9aa3" stroke-dasharray="5 4"/>
        ${tps.map((_, i) => `<line x1="138" y1="${65-i*20}" x2="224" y2="${65-i*20}" stroke="#35bf86" stroke-dasharray="5 4"/>`).join("")}
        <circle cx="82" cy="72" r="5" fill="#fff" stroke="#1ba971" stroke-width="2"/>
        <circle cx="176" cy="38" r="5" fill="#fff" stroke="#2f66e8" stroke-width="2"/>
      </svg>
    </div>`;
  }

  function signalCard(item) {
    return `<article class="s24-card ${state.selectedSignal?.id === item.id ? "selected" : ""}" data-signal-id="${item.id}">
      <div class="s24-card-head"><div><div class="s24-card-title">${esc(item.symbol || "Signal #" + item.id)} · ${esc(item.side || "—")}</div><div class="s24-card-sub">${esc(item.source_name || item.source_method)} · ${faDate(item.created_at)}</div></div><span class="s24-card-badge">${esc(item.status)}</span></div>
      ${miniSignal(item)}
      <div class="s24-card-actions"><span class="s24-card-sub">Entry ${n(item.entry)}</span><button type="button" data-signal-archive="${item.id}">${item.archived_at ? "بازگردانی" : "بایگانی"}</button></div>
    </article>`;
  }

  function signalTable(items) {
    return `<div class="s24-table-scroll"><table class="s24-table"><thead><tr><th>بازار</th><th>جهت</th><th>Entry</th><th>TP</th><th>SL</th><th>وضعیت</th><th>زمان</th><th></th></tr></thead><tbody>
      ${items.map((item) => `<tr data-signal-id="${item.id}"><td>${esc(item.symbol || "—")}</td><td>${esc(item.side || "—")}</td><td>${n(item.entry)}</td><td>${(item.targets || []).map(t => n(t.price)).join(" / ") || "—"}</td><td>${n(item.stop_loss)}</td><td>${esc(item.status)}</td><td>${faDate(item.created_at)}</td><td><button class="s24-button ghost" data-signal-archive="${item.id}">${item.archived_at ? "بازگردانی" : "بایگانی"}</button></td></tr>`).join("")}
    </tbody></table></div>`;
  }

  function bindSignalList() {
    qsa("[data-signal-id]", qs("[data-signal-list]")).forEach((node) => {
      node.addEventListener("click", (event) => {
        if (event.target.closest("[data-signal-archive]")) return;
        const item = state.signals.find((x) => x.id === Number(node.dataset.signalId));
        if (item) selectSignal(item);
      });
    });
    qsa("[data-signal-archive]", qs("[data-signal-list]")).forEach((button) => {
      button.addEventListener("click", async (event) => {
        event.stopPropagation();
        const item = state.signals.find((x) => x.id === Number(button.dataset.signalArchive));
        if (!item) return;
        button.disabled = true;
        try {
          await api(appPath(`/api/v1/inbox/${item.id}/archive/`), {
            method: "POST", body: JSON.stringify({ archived: !item.archived_at })
          });
          toast(item.archived_at ? "سیگنال به فهرست فعال برگشت." : "سیگنال بایگانی شد.");
          await loadSignals();
        } catch (error) { toast(error.message, true); }
        finally { button.disabled = false; }
      });
    });
  }

  function renderSignals() {
    const list = qs("[data-signal-list]");
    if (!state.signals.length) {
      list.className = "s24-empty-inline";
      list.innerHTML = "در این فیلتر سیگنالی وجود ندارد.";
      return;
    }
    if (state.signalLayout === "cards") {
      list.className = "s24-card-grid";
      list.innerHTML = state.signals.map(signalCard).join("");
    } else {
      list.className = "";
      list.innerHTML = signalTable(state.signals);
    }
    bindSignalList();
  }

  async function loadSignals() {
    try {
      const payload = await api(appPath(`/api/v1/inbox/?view=${state.signalView}`));
      state.signals = payload.items || [];
      if (state.selectedSignal && !state.signals.some(x => x.id === state.selectedSignal.id)) {
        state.selectedSignal = null;
      }
      renderSignals();
      if (!state.selectedSignal && state.signals.length) selectSignal(state.signals[0]);
    } catch (error) {
      qs("[data-signal-list]").innerHTML = `<div class="s24-empty-inline">${esc(error.message)}</div>`;
    }
  }

  function signalScheme(detail) {
    const s = detail.signal;
    const st = s.structured || {};
    const targets = st.targets || [];
    const status = s.outcome?.status || s.status;
    const line = (label, price, cls, top) => `<div class="s24-scheme-line ${cls}" style="top:${top}%"><span>${esc(label)} ${n(price)}</span></div>`;
    return `<div class="s24-scheme">
      ${targets.slice(0,3).map((t,i)=>line("TP"+t.position,t.price,"",18+i*16)).join("")}
      ${line("Entry",st.entry,"",72)}
      ${line("SL",st.stop_loss,"sl",88)}
      <svg viewBox="0 0 220 170" preserveAspectRatio="none" aria-hidden="true"><path d="M5 130 C34 158 53 106 80 120 C106 134 119 72 145 82 C168 90 181 37 215 22" fill="none" stroke="#2e66e8" stroke-width="3"/></svg>
      <i class="dot" style="left:34%;top:70%"></i><i class="dot" style="left:68%;top:35%"></i>
    </div>
    <div class="s24-detail-facts">
      <div class="s24-fact"><span>وضعیت</span><strong>${esc(status)}</strong></div>
      <div class="s24-fact"><span>جهت</span><strong>${esc(st.side || "—")}</strong></div>
      <div class="s24-fact"><span>Entry</span><strong>${n(st.entry)}</strong></div>
      <div class="s24-fact"><span>Stop Loss</span><strong>${n(st.stop_loss)}</strong></div>
    </div>`;
  }

  async function selectSignal(item) {
    state.selectedSignal = item;
    renderSignals();
    qs("[data-signal-symbol]").textContent = item.symbol || ("Signal #" + item.id);
    qs("[data-signal-source]").textContent = item.source_name || item.source_method || "—";
    try {
      const detail = await api(appPath(`/api/v1/inbox/${item.id}/`));
      state.selectedSignalDetail = detail;
      qs("[data-signal-status]").textContent = detail.signal.outcome?.status || detail.signal.status;
      qs("[data-signal-detail]").innerHTML = signalScheme(detail);
      if (item.market_id) {
        await chartFor(
          { market: item.market_id, signal: item.id, interval: "5m", bars: 180 },
          qs("[data-signal-chart]"), qs("[data-signal-chart-empty]")
        );
      } else {
        qs("[data-signal-chart-empty]").hidden = false;
        qs("[data-signal-chart-empty]").textContent = "این سیگنال هنوز به بازار مشخصی متصل نشده است.";
      }
    } catch (error) { toast(error.message, true); }
  }

  function tradeRow(row) {
    const originClass = row.origin === "external" ? "external" : "";
    return `<tr data-trade-key="${esc(row.key)}">
      <td><strong dir="ltr">${esc(row.symbol || "—")}</strong><br><small>${esc(row.exchange || "")}</small></td>
      <td><span class="origin ${originClass}">${esc(row.origin_label)}</span></td>
      <td>${esc(row.side || "—")}</td><td>${n(row.entry)}</td><td>${esc(row.state || "—")}</td>
      <td>${faDate(row.updated_at)}</td>
      <td><button type="button" class="s24-button ghost" data-trade-archive="${esc(row.key)}">${row.archived_at ? "بازگردانی" : "حذف از دید"}</button></td>
    </tr>`;
  }

  function renderTrades() {
    qs("[data-trade-list]").innerHTML = state.trades.map(tradeRow).join("") || '<tr><td colspan="7">معامله‌ای در این فیلتر نیست.</td></tr>';
    qs("[data-trade-count]").textContent = state.trades.length + " رکورد";
    qsa("[data-trade-key]", qs("[data-trade-list]")).forEach((row) => {
      row.addEventListener("click", (event) => {
        if (event.target.closest("[data-trade-archive]")) return;
        const item = state.trades.find((x) => x.key === row.dataset.tradeKey);
        if (item) selectTrade(item);
      });
    });
    qsa("[data-trade-archive]", qs("[data-trade-list]")).forEach((button) => {
      button.addEventListener("click", async (event) => {
        event.stopPropagation();
        const item = state.trades.find((x) => x.key === button.dataset.tradeArchive);
        if (!item) return;
        try {
          await api(appPath("/api/v1/trades/archive/"), {
            method: "POST",
            body: JSON.stringify({ kind: item.kind, id: item.id, archived: !item.archived_at })
          });
          toast(item.archived_at ? "معامله به فهرست بازگشت." : "معامله بایگانی شد؛ داده آن حذف نشد.");
          await loadTrades();
        } catch (error) { toast(error.message, true); }
      });
    });
  }

  async function loadTrades() {
    try {
      const payload = await api(appPath(`/api/v1/trades/?view=${state.tradeView}`));
      state.trades = payload.trades || [];
      renderTrades();
      if (!state.selectedTrade && state.trades.length) selectTrade(state.trades[0]);
    } catch (error) {
      qs("[data-trade-list]").innerHTML = `<tr><td colspan="7">${esc(error.message)}</td></tr>`;
    }
  }

  function tradeDetail(row) {
    const levels = (row.tp || []).map((v,i)=>`<div class="s24-level tp"><b>TP${i+1}</b><span>${n(v)}</span></div>`).join("");
    return `<div class="hero"><span>${esc(row.origin_label)}</span><strong dir="ltr">${esc(row.symbol || "—")}</strong><span>${esc(row.exchange || "")} · ${esc(row.side || "")}</span></div>
      <div class="s24-trade-levels"><div class="s24-level"><b>Entry</b><span>${n(row.entry)}</span></div><div class="s24-level"><b>Amount</b><span>${n(row.amount)}</span></div>${levels}${row.stop_loss ? `<div class="s24-level sl"><b>Stop Loss</b><span>${n(row.stop_loss)}</span></div>` : ""}</div>
      <div class="s24-fact"><span>وضعیت</span><strong>${esc(row.state || "—")}</strong></div>`;
  }

  async function selectTrade(row) {
    state.selectedTrade = row;
    qs("[data-trade-symbol]").textContent = row.symbol || row.key;
    qs("[data-trade-origin]").textContent = row.origin_label || "—";
    qs("[data-trade-status]").textContent = row.state || "—";
    qs("[data-trade-detail]").innerHTML = tradeDetail(row);
    const canvas = qs("[data-trade-chart]"), empty = qs("[data-trade-chart-empty]");
    if (!row.market_id) {
      empty.hidden = false; empty.textContent = "برای این رکورد خارجی هنوز بازار متناظر همگام نشده است.";
      drawChart(canvas, { candles: [] }, empty); return;
    }
    const params = { market: row.market_id, interval: "5m", bars: 180 };
    if (row.kind === "paper") params.trade = row.id;
    if (row.kind === "external") params.external = row.id;
    try { await chartFor(params, canvas, empty); } catch (error) { empty.hidden = false; empty.textContent = error.message; }
  }

  async function refreshTrades() {
    const button = qs("[data-trades-refresh]");
    const stateNode = qs("[data-trade-refresh-state]");
    button.disabled = true; stateNode.textContent = "در حال Sync واقعی صرافی…";
    try {
      const payload = await api(appPath("/api/v1/trades/refresh/"), { method: "POST", body: "{}" });
      stateNode.textContent = `آخرین Sync: ${faDate(payload.as_of)} · ${payload.open} باز`;
      state.trades = payload.trades || [];
      renderTrades();
      toast("اطلاعات حساب‌ها و معاملات از صرافی تازه‌سازی شد.");
    } catch (error) {
      stateNode.textContent = "خطا در تازه‌سازی";
      toast(error.message, true);
    } finally { button.disabled = false; }
  }

  let marketTimer = null;

  function chooseMarket(button) {
    state.market = {
      id: Number(button.dataset.marketId),
      symbol: button.dataset.marketSymbol,
      exchange: button.dataset.marketExchange,
    };
    const box = qs("[data-market-results]");
    qs("[data-market-hidden]").value = String(state.market.id);
    qs("[data-market-search]").value = state.market.symbol;
    qs("[data-newtrade-symbol]").textContent = state.market.symbol;
    qs("[data-newtrade-exchange]").textContent = state.market.exchange;
    if (box) box.hidden = true;
    loadNewTradeChart();
  }

  async function searchMarkets(term = "") {
    const box = qs("[data-market-results]");
    const account = qs("[data-account-select]");
    if (!box || !account || !account.value) {
      if (box) {
        box.hidden = false;
        box.innerHTML = "<div class='s24-empty-inline'>ابتدا حساب صرافی را انتخاب کنید.</div>";
      }
      return;
    }
    try {
      const query = new URLSearchParams({account: account.value, q: term.trim()});
      const payload = await api(appPath("/api/v1/markets/search/?") + query.toString());
      const rows = payload.results || [];
      box.innerHTML = rows.map((m) =>
        `<button type="button" data-market-id="${m.id}" data-market-symbol="${esc(m.symbol)}" data-market-exchange="${esc(m.exchange)}">
           <strong dir="ltr">${esc(m.symbol)}</strong>
           <span>${esc(m.exchange_name)} · ${esc(m.market_type)}${m.metadata_fresh ? " · synced" : ""}</span>
         </button>`
      ).join("") || "<div class='s24-empty-inline'>برای این حساب بازار خوانا پیدا نشد؛ Sync صرافی یا مجوز Read را بررسی کنید.</div>";
      box.hidden = false;
      qsa("[data-market-id]", box).forEach((button) => button.addEventListener("click", () => chooseMarket(button)));
    } catch (error) {
      box.hidden = false;
      box.innerHTML = `<div class="s24-empty-inline">${esc(error.message)}</div>`;
    }
  }

  async function loadNewTradeChart() {
    if (!state.market) return;
    try {
      const payload = await chartFor(
        { market: state.market.id, interval: state.interval, bars: 220 },
        qs("[data-newtrade-chart]"), qs("[data-newtrade-empty]")
      );
      const provider = qs("[data-market-provider]");
      if (provider) provider.textContent = payload.provider_label || payload.provider || "public market data";
      const last = payload.candles?.at(-1);
      const entry = qs('[data-newtrade-form] [name="entry_price"]');
      if (last && entry && !entry.value) entry.value = last.close;
    } catch (error) {
      qs("[data-newtrade-empty]").hidden = false;
      qs("[data-newtrade-empty]").textContent = error.message;
    }
  }

  async function submitTrade(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const status = qs("[data-newtrade-status]");
    if (!state.market) { status.textContent = "بازار را انتخاب کنید."; return; }
    const fd = new FormData(form);
    const body = {
      account: fd.get("account"), market: String(state.market.id), source: "manual",
      side: fd.get("side"), entry_price: fd.get("entry_price"),
      tp1: fd.get("tp1"), tp2: fd.get("tp2") || "", tp3: fd.get("tp3") || "",
      stop_loss: fd.get("stop_loss"), capital: fd.get("capital"), leverage: "1",
      trailing_sl: fd.get("trailing_sl") === "on",
      percentage_trailing: fd.get("percentage_trailing") === "on",
      trailing_trigger: fd.get("trailing_trigger") || "tp1",
      trailing_distance: fd.get("trailing_distance") || "1",
      client_token: crypto.randomUUID(),
    };
    status.textContent = "در حال ساخت برنامه معامله…";
    try {
      const payload = await api(appPath("/api/v1/manual/plans/"), {method:"POST", body:JSON.stringify(body)});
      status.innerHTML = `برنامه #${payload.plan.id} ساخته شد. <a href="${appPath(`/manual/${payload.plan.id}/`)}">مشاهده و تأیید</a>`;
      toast("برنامه معامله ساخته شد.");
    } catch (error) {
      status.textContent = error.message;
      toast(error.message, true);
    }
  }

  function restartPolling() {
    if (state.poller) clearInterval(state.poller);
    state.poller = setInterval(() => {
      loadTicker();
      if (document.hidden) return;
      if (state.route === "overview") loadOverview();
      if (state.route === "inbox" && state.selectedSignal?.market_id) {
        chartFor({ market: state.selectedSignal.market_id, signal: state.selectedSignal.id, interval: "5m", bars: 180 }, qs("[data-signal-chart]"), qs("[data-signal-chart-empty]")).catch(()=>{});
      }
      if (state.route === "trades" && state.selectedTrade?.market_id) selectTrade(state.selectedTrade);
      if (state.route === "newtrade" && state.market) loadNewTradeChart();
    }, 5000);
  }

  qs("[data-signal-view]").addEventListener("click", (e) => {
    const button = e.target.closest("[data-view]"); if (!button) return;
    state.signalView = button.dataset.view; setActive(e.currentTarget, "view", state.signalView); state.selectedSignal = null; loadSignals();
  });
  qs("[data-signal-layout]").addEventListener("click", (e) => {
    const button = e.target.closest("[data-layout]"); if (!button) return;
    state.signalLayout = button.dataset.layout; setActive(e.currentTarget, "layout", state.signalLayout); renderSignals();
  });
  qs("[data-signals-reload]").addEventListener("click", loadSignals);
  qs("[data-trade-view]").addEventListener("click", (e) => {
    const button = e.target.closest("[data-view]"); if (!button) return;
    state.tradeView = button.dataset.view; setActive(e.currentTarget, "view", state.tradeView); state.selectedTrade = null; loadTrades();
  });
  qs("[data-trades-refresh]").addEventListener("click", refreshTrades);
  qs("[data-newtrade-interval]").addEventListener("click", (e) => {
    const button = e.target.closest("[data-interval]"); if (!button) return;
    state.interval = button.dataset.interval; setActive(e.currentTarget, "interval", state.interval); loadNewTradeChart();
  });
  qs("[data-account-select]")?.addEventListener("change", () => {
    state.market = null;
    qs("[data-market-hidden]").value = "";
    qs("[data-market-search]").value = "";
    qs("[data-newtrade-symbol]").textContent = "بازار را انتخاب کنید";
    qs("[data-newtrade-exchange]").textContent = "—";
    searchMarkets("");
  });
  qs("[data-market-search]")?.addEventListener("focus", (e) => searchMarkets(e.target.value));
  qs("[data-market-search]")?.addEventListener("input", (e) => {
    clearTimeout(marketTimer); marketTimer = setTimeout(() => searchMarkets(e.target.value), 180);
  });
  qs("[data-newtrade-form]")?.addEventListener("submit", submitTrade);
  window.addEventListener("hashchange", route);
  window.addEventListener("resize", () => {
    if (state.route === "inbox" && state.selectedSignal) selectSignal(state.selectedSignal);
    if (state.route === "trades" && state.selectedTrade) selectTrade(state.selectedTrade);
    if (state.route === "newtrade" && state.market) loadNewTradeChart();
  });
  document.addEventListener("visibilitychange", restartPolling);

  loadTicker(true);
  route();
  restartPolling();
})();
