import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity, AlertTriangle, ArrowLeftRight, Bell, ChartCandlestick, ChevronLeft,
  ChevronRight, CircleDollarSign, FileBarChart, LayoutDashboard, LogOut,
  Menu, MessageCircle, PlusCircle, Radar, Settings, ShieldCheck, Sparkles,
  UserCircle2, WalletCards, X, PlugZap, Inbox, SlidersHorizontal
} from "lucide-react";
import "./styles.css";

const base = (document.documentElement.dataset.basePath || "/cryptosniper/").replace(/\/+$/, "/");
const api = (path) => base + path.replace(/^\/+/, "");
const pathOf = () => location.pathname.replace(base.replace(/\/$/, ""), "") || "/";

function csrfToken() {
  const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

export async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  if (options.body && !(options.body instanceof FormData) && typeof options.body !== "string") {
    headers.set("Content-Type", "application/json");
    options = { ...options, body: JSON.stringify(options.body) };
  }
  if (!["GET", "HEAD"].includes((options.method || "GET").toUpperCase())) {
    headers.set("X-CSRFToken", csrfToken());
  }
  const response = await fetch(api(path), { credentials: "same-origin", ...options, headers });
  const type = response.headers.get("content-type") || "";
  const payload = type.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const error = new Error(payload?.error || payload?.detail || "درخواست ناموفق بود.");
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

const items = [
  ["/dashboard/", "نمای کلی", LayoutDashboard],
  ["/trades/", "معاملات", ArrowLeftRight],
  ["/manual/new/", "معامله دستی", PlusCircle],
  ["/smart-paste/", "تحلیل سیگنال", Sparkles],
  ["/inbox/", "صندوق سیگنال‌ها", Inbox],
  ["/exchanges/", "صرافی‌ها", PlugZap],
  ["/watchlist/", "دیده‌بان و بازارها", Radar],
  ["/settings/telegram/", "تلگرام و سیگنال‌ها", MessageCircle],
  ["/alerts/", "هشدارها", Bell],
  ["/reports/", "گزارش عملکرد", FileBarChart],
  ["/operations/", "مرکز عملیات", Activity],
  ["/settings/profile/", "تنظیمات", Settings],
];

function activeFor(href) {
  const current = location.pathname;
  if (href === "/dashboard/") return current.endsWith("/dashboard/");
  const target = base.replace(/\/$/, "") + href;
  return current.startsWith(target);
}

function Shell() {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("cs.sidebar") === "1");
  const [mobile, setMobile] = useState(false);
  const [notifications, setNotifications] = useState(0);
  const user = document.documentElement.dataset.userName || "کاربر";

  useEffect(() => {
    document.body.classList.toggle("cs-sidebar-collapsed", collapsed);
    localStorage.setItem("cs.sidebar", collapsed ? "1" : "0");
  }, [collapsed]);

  useEffect(() => {
    let alive = true;
    request("api/v1/notifications/")
      .then((data) => {
        if (!alive) return;
        const rows = data.items || data.notifications || [];
        setNotifications(rows.filter((x) => !x.read_at && x.read !== true).length);
      })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  const go = (href) => {
    setMobile(false);
    location.href = base.replace(/\/$/, "") + href;
  };

  return <>
    <button className={"cs-scrim " + (mobile ? "show" : "")} onClick={() => setMobile(false)} aria-label="بستن منو"/>
    <aside className={"cs-sidebar " + (collapsed ? "collapsed " : "") + (mobile ? "mobile-open" : "")}>
      <div className="cs-brand" onClick={() => go("/dashboard/")}>
        <span className="cs-logo"><ChartCandlestick size={22}/></span>
        {!collapsed && <span><b>CryptoSniper</b><small>مرکز کنترل معاملات</small></span>}
      </div>
      <button className="cs-collapse" onClick={() => setCollapsed((x) => !x)} aria-label="جمع‌کردن سایدبار">
        {collapsed ? <ChevronLeft size={18}/> : <ChevronRight size={18}/>}
      </button>
      <nav className="cs-nav">
        {items.map(([href, label, Icon]) => (
          <button key={href} className={"cs-nav-item " + (activeFor(href) ? "active" : "")}
            onClick={() => go(href)} title={label}>
            <Icon size={19}/>{!collapsed && <span>{label}</span>}
          </button>
        ))}
      </nav>
      <div className="cs-side-foot">
        <button className="cs-nav-item" onClick={() => go("/settings/profile/")}><UserCircle2 size={19}/>{!collapsed && <span>{user}</span>}</button>
        <form action={api("auth/logout/")} method="post">
          <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken()}/>
          <button className="cs-nav-item cs-danger" type="submit"><LogOut size={19}/>{!collapsed && <span>خروج</span>}</button>
        </form>
      </div>
    </aside>
    <header className="cs-topbar">
      <div className="cs-top-start">
        <button className="cs-icon mobile-only" onClick={() => setMobile(true)} aria-label="منو"><Menu size={20}/></button>
        <div><b>{document.documentElement.dataset.pageTitle || "CryptoSniper"}</b><small>همه حساب‌ها و معاملات در یک مرکز کنترل</small></div>
      </div>
      <div className="cs-top-actions">
        <a className="cs-icon cs-notification" href={api("notifications/")} aria-label="اعلان‌ها">
          <Bell size={19}/>{notifications > 0 && <span>{Math.min(notifications, 99)}</span>}
        </a>
        <button className="cs-primary" onClick={() => go("/manual/new/")}><PlusCircle size={18}/> معامله جدید</button>
      </div>
    </header>
  </>;
}

function ErrorBoundary({ children }) {
  const [error, setError] = useState(null);
  useEffect(() => {
    const handler = (event) => setError(event.reason || event.error || new Error("خطای رابط"));
    addEventListener("unhandledrejection", handler);
    addEventListener("error", handler);
    return () => {
      removeEventListener("unhandledrejection", handler);
      removeEventListener("error", handler);
    };
  }, []);
  if (error) return <div className="cs-error"><AlertTriangle size={20}/><div><b>رابط این بخش کامل بارگذاری نشد.</b><span>{String(error.message || error)}</span></div></div>;
  return children;
}

function mount(id, Component) {
  const node = document.getElementById(id);
  if (node) createRoot(node).render(<ErrorBoundary><Component/></ErrorBoundary>);
}

const shell = document.getElementById("cs-shell-root");
if (shell) createRoot(shell).render(<Shell/>);

export { mount, api, csrfToken };
