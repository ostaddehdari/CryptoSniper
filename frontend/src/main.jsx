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


const money = (value, digits = 2) => {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("fa-IR", { maximumFractionDigits: digits, minimumFractionDigits: digits }) : "—";
};

function Loading() {
  return <div className="cs-panel cs-loading"><span/><span/><span/></div>;
}
function Empty({children}) { return <div className="cs-empty">{children}</div>; }

function DashboardPage() {
  const [data, setData] = useState(null);
  const [tab, setTab] = useState("balances");
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    request("api/v1/dashboard/").then(setData).catch((e) => setError(e.message));
  }, []);
  if (error) return <div className="cs-panel cs-error"><AlertTriangle size={20}/><span>{error}</span></div>;
  if (!data) return <Loading/>;
  const valuation = data.accounts.reduce((sum, row) => sum + Number(row.known_valuation || 0), 0);
  const freeUsdt = data.accounts.reduce((sum, row) => sum + Number(row.free_usdt || 0), 0);
  const tabs = [["balances","موجودی‌ها"],["trades","آخرین معاملات"],["signals","آخرین سیگنال‌ها"],["alerts","آخرین هشدارها"]];
  return <div className="cs-page">
    <div className="cs-metrics">
      <Metric icon={WalletCards} label="ارزش شناخته‌شده دارایی‌ها" value={money(valuation) + " USDT"} hint={data.cache_ok ? "قیمت‌های تازه" : "بخشی از قیمت‌ها قدیمی است"}/>
      <Metric icon={CircleDollarSign} label="تتر آزاد لحظه‌ای" value={money(freeUsdt) + " USDT"} hint="جمع حساب‌های متصل"/>
      <Metric icon={PlugZap} label="حساب‌های متصل" value={String(data.connected_accounts)} hint={data.accounts.length + " حساب ثبت‌شده"}/>
      <Metric icon={ArrowLeftRight} label="سفارش‌های باز" value={String(data.open_trades)} hint="CryptoSniper و صرافی"/>
      <Metric icon={FileBarChart} label="سود/زیان خالص ماه" value={data.monthly_net_pnl == null ? "—" : money(data.monthly_net_pnl) + " " + (data.accounts[0]?.base_currency || "USDT")} hint={data.monthly_net_complete ? "محاسبه کامل" : "فقط داده‌های قابل محاسبه"}/>
    </div>
    <div className="cs-grid-two">
      <section className="cs-panel">
        <div className="cs-panel-head"><div><h2>حساب‌ها و موجودی</h2><p>USDT آزاد به‌صورت خلاصه؛ سایر ارزها در صورت نیاز باز می‌شوند.</p></div><button className="cs-soft" onClick={() => setExpanded((x) => !x)}>{expanded ? "بستن جزئیات" : "تمام موجودی‌ها"}</button></div>
        <div className="cs-table-wrap"><table><thead><tr><th>صرافی</th><th>حساب</th><th>USDT آزاد</th><th>ارزش شناخته‌شده</th><th>وضعیت</th></tr></thead><tbody>
          {data.accounts.map((a) => <React.Fragment key={a.id}><tr><td><b>{a.exchange}</b></td><td>{a.label}</td><td className="cs-emph">{money(a.free_usdt)}</td><td>{money(a.known_valuation)}</td><td><Status value={a.status}/></td></tr>
          {expanded && <tr className="cs-detail-row"><td colSpan="5"><div className="cs-assets">{a.balances.map((b,i)=><span key={i}><b>{b.asset}</b> آزاد {money(b.free, Math.abs(Number(b.free)) < 1 ? 6 : 2)} · قفل {money(b.locked, Math.abs(Number(b.locked)) < 1 ? 6 : 2)}</span>)}</div></td></tr>}</React.Fragment>)}
        </tbody></table></div>
      </section>
      <section className="cs-panel cs-chart-card">
        <div className="cs-panel-head"><div><h2>وضعیت نقدینگی USDT</h2><p>جمع موجودی آزاد حساب‌های قابل‌خواندن</p></div><b className="cs-up">{money(freeUsdt)} USDT</b></div>
        <SparkChart/>
      </section>
    </div>
    <section className="cs-panel">
      <div className="cs-tabs">{tabs.map(([id,label])=><button className={tab===id?"active":""} key={id} onClick={()=>setTab(id)}>{label}</button>)}</div>
      {tab==="balances" && <div className="cs-tab-body"><div className="cs-assets-grid">{data.accounts.flatMap(a=>a.balances.slice(0,6).map((b,i)=><div className="cs-asset-card" key={a.id+"-"+i}><span>{a.exchange}</span><b>{b.asset}</b><strong>{money(b.free, Math.abs(Number(b.free))<1?6:2)}</strong></div>))}</div></div>}
      {tab==="trades" && <OrdersTable rows={data.recent_orders}/>}
      {tab==="signals" && <div className="cs-list">{data.recent_signals.length ? data.recent_signals.map(x=><a href={api("inbox/"+x.id+"/")} key={x.id}><div><b>{x.source}</b><span>{x.side || "—"} · {x.status}</span></div><small>{x.entry ? "ورود "+money(x.entry,6):"نیازمند بررسی"}</small></a>) : <Empty>سیگنال فعالی ثبت نشده است.</Empty>}</div>}
      {tab==="alerts" && <div className="cs-list">{data.recent_alerts.length ? data.recent_alerts.map(x=><a href={api("alerts/")} key={x.id}><div><b>{x.market}</b><span>{x.enabled?"فعال":"غیرفعال"}</span></div></a>) : <Empty>هشداری ثبت نشده است.</Empty>}</div>}
    </section>
  </div>;
}
function Metric({icon:Icon,label,value,hint}) { return <article className="cs-panel cs-metric"><div><span className="cs-metric-icon"><Icon size={20}/></span><label>{label}</label></div><strong>{value}</strong><small>{hint}</small></article>; }
function Status({value}) { const cls=value==="connected"?"ok":value==="error"?"bad":"warn"; const label={connected:"متصل",restricted:"محدود",pending:"در انتظار",error:"خطا",disabled:"غیرفعال"}[value]||value; return <span className={"cs-status "+cls}>{label}</span>; }
function SparkChart(){return <div className="cs-spark"><svg viewBox="0 0 650 190" preserveAspectRatio="none"><defs><linearGradient id="csG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#2f66d8" stopOpacity=".24"/><stop offset="1" stopColor="#2f66d8" stopOpacity=".01"/></linearGradient></defs><path d="M0,145 C45,137 72,151 105,126 S170,138 208,111 S267,124 310,93 S377,104 422,82 S482,93 521,59 S590,75 650,40 L650,190 L0,190 Z" fill="url(#csG)"/><path d="M0,145 C45,137 72,151 105,126 S170,138 208,111 S267,124 310,93 S377,104 422,82 S482,93 521,59 S590,75 650,40" fill="none" stroke="#2f66d8" strokeWidth="3"/></svg></div>}

function OrdersTable({rows=[]}) {
  if (!rows.length) return <Empty>هنوز سفارش واقعی ثبت‌شده‌ای برای نمایش وجود ندارد.</Empty>;
  return <div className="cs-table-wrap"><table><thead><tr><th>بازار</th><th>صرافی</th><th>جهت</th><th>قیمت</th><th>مقدار</th><th>وضعیت</th></tr></thead><tbody>{rows.map(x=><tr key={x.id}><td><b>{(x.market||"").replace("/USDT","")}</b></td><td>{x.exchange}</td><td>{x.side==="buy"?"خرید":"فروش"}</td><td>{money(x.average_price||x.price,8)}</td><td>{money(x.amount,8)}</td><td><Status value={x.state}/></td></tr>)}</tbody></table></div>;
}

function TradesPage() {
  const [data,setData]=useState(null), [error,setError]=useState("");
  useEffect(()=>{request("api/v1/trades/").then(setData).catch(e=>setError(e.message));},[]);
  if(error) return <div className="cs-panel cs-error">{error}</div>;
  if(!data) return <Loading/>;
  return <div className="cs-page">
    <div className="cs-page-head"><div><h1>همه معاملات و سفارش‌ها</h1><p>سفارش‌های ثبت‌شده توسط CryptoSniper و موارد مشاهده‌شده مستقیم در صرافی، یکجا.</p></div><a className="cs-primary" href={api("manual/new/")}><PlusCircle size={18}/> معامله جدید</a></div>
    <section className="cs-panel"><div className="cs-panel-head"><div><h2>سفارش‌های CryptoSniper</h2><p>وضعیت مستقیم از دیتابیس سفارش‌های واقعی.</p></div></div><OrdersTable rows={data.orders}/></section>
    <section className="cs-panel"><div className="cs-panel-head"><div><h2>معاملات و سفارش‌های خارجی</h2><p>فقط پایش؛ مواردی که مستقیماً در خود صرافی ایجاد شده‌اند.</p></div><span className="cs-status warn">External Trade</span></div>
      {data.external.length ? <div className="cs-external-grid">{data.external.map(x=><a className="cs-external-card" href={api("external/"+x.id+"/")} key={x.id}><div><b>{x.payload.symbol || "—"}</b><span>{x.exchange}</span></div><small>{x.kind} · {x.payload.status || "مشاهده‌شده"}</small></a>)}</div> : <Empty>در آخرین همگام‌سازی، معامله خارجی قابل‌نمایشی ثبت نشده است.</Empty>}
    </section>
  </div>;
}

mount("cs-dashboard-root", DashboardPage);
mount("cs-trades-root", TradesPage);
