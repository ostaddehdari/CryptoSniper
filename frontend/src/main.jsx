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


function trimNumber(value, max = 8) {
  if (value === null || value === undefined || value === "") return "";
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return n.toLocaleString("en-US", {useGrouping:false, maximumFractionDigits:max});
}
function pct(entry, target, side) {
  const e=Number(entry), t=Number(target);
  if(!e || !t) return null;
  const raw=(t-e)/e*100;
  return side==="short" ? -raw : raw;
}
function TargetField({label,value,onChange,entry,side}) {
  const p=pct(entry,value,side);
  return <label className="cs-field"><span>{label}</span><div className="cs-input-suffix"><input inputMode="decimal" value={value} onChange={e=>onChange(e.target.value)}/><i>USDT</i></div>{p!==null&&<small className={p>=0?"cs-up":"cs-down"}>{p>=0?"+":""}{money(p,2)}٪ نسبت به ورود</small>}</label>;
}
function SearchSelect({items,value,onChange,placeholder="انتخاب کنید",renderLabel=(x)=>x.label||x.name||x.asset}) {
  const [open,setOpen]=useState(false), [q,setQ]=useState("");
  const selected=items.find(x=>String(x.id)===String(value));
  const filtered=items.filter(x=>renderLabel(x).toLowerCase().includes(q.toLowerCase())).slice(0,80);
  return <div className="cs-search-select">
    <button type="button" className="cs-select-button" onClick={()=>setOpen(x=>!x)}>{selected?renderLabel(selected):placeholder}<ChevronRight size={15}/></button>
    {open&&<div className="cs-select-pop"><input autoFocus placeholder="جست‌وجو..." value={q} onChange={e=>setQ(e.target.value)}/><div>{filtered.map(x=><button type="button" key={x.id} onClick={()=>{onChange(String(x.id));setOpen(false);setQ("");}}>{renderLabel(x)}</button>)}</div></div>}
  </div>;
}

function ManualPage() {
  const [accounts,setAccounts]=useState([]), [markets,setMarkets]=useState([]), [account,setAccount]=useState(""), [market,setMarket]=useState("");
  const [side,setSide]=useState("long"), [entry,setEntry]=useState(""), [sl,setSl]=useState(""), [tp1,setTp1]=useState(""), [tp2,setTp2]=useState(""), [tp3,setTp3]=useState("");
  const [leverage,setLeverage]=useState("1"), [capital,setCapital]=useState(""), [risk,setRisk]=useState("1"), [fix,setFix]=useState(null);
  const [message,setMessage]=useState(""), [saving,setSaving]=useState(false);
  const selectedMarket=markets.find(x=>String(x.id)===String(market));
  useEffect(()=>{request("api/v1/exchanges/").then(data=>{
    const rows=(data.accounts||[]).filter(x=>x.environment==="live" && !["binance","simulator"].includes(String(x.exchange_code||x.exchange||"").toLowerCase()));
    setAccounts(rows);
    if(rows[0]) setAccount(String(rows[0].id));
  }).catch(e=>setMessage(e.message));},[]);
  useEffect(()=>{if(!account){setMarkets([]);return;} request("api/v1/manual/markets/?account="+encodeURIComponent(account)).then(data=>{setMarkets(data.markets||[]);setMarket(data.markets?.[0]?String(data.markets[0].id):"");}).catch(e=>{setMarkets([]);setMessage(e.message);});},[account]);
  useEffect(()=>{if(selectedMarket?.price && !entry) setEntry(trimNumber(selectedMarket.price,8));},[market,selectedMarket?.price]);
  useEffect(()=>{setFix(null);},[account,market,entry,sl,side,leverage,risk]);
  const calcFix=async()=>{if(!account||!market||!entry||!sl)return;try{setFix(await request("api/v1/manual/fix-loss/",{method:"POST",body:{account_id:Number(account),market_id:Number(market),entry,stop_loss:sl,side,leverage,risk_percent:risk}}));}catch(e){setMessage(e.message);}};
  const save=async()=>{setMessage("");setSaving(true);try{
    const result=await request("api/v1/manual/plans/",{method:"POST",body:{account:Number(account),market:Number(market),source:"manual",side,entry_price:entry,tp1,tp2:tp2||"",tp3:tp3||"",stop_loss:sl,capital:capital||fix?.suggested_notional||"",leverage,trailing_sl:true,percentage_trailing:true,trailing_distance:"1",client_token:crypto.randomUUID()}});
    location.href=api("manual/"+result.plan.id+"/");
  }catch(e){setMessage(e.payload?.errors?JSON.stringify(e.payload.errors):e.message);}finally{setSaving(false);}};
  const marketLabel=m=>m.asset+(m.market_type==="margin"&&Number(m.max_leverage)>1?"  x"+trimNumber(m.max_leverage,0):"");
  return <div className="cs-manual-layout">
    <section className="cs-panel">
      <div className="cs-panel-head"><div><h2>ثبت معامله جدید</h2><p>ابتدا حساب اصلی و سپس بازار همان صرافی را انتخاب کنید.</p></div>{selectedMarket&&!selectedMarket.price_stale&&<span className="cs-live-dot">قیمت زنده</span>}</div>
      {message&&<div className="cs-inline-error">{message}</div>}
      <div className="cs-form-grid">
        <label className="cs-field"><span>حساب صرافی</span><SearchSelect items={accounts} value={account} onChange={setAccount} renderLabel={x=>(x.exchange_name||x.exchange||"صرافی")+" · "+x.label}/></label>
        <label className="cs-field"><span>ارز</span><SearchSelect items={markets} value={market} onChange={setMarket} renderLabel={marketLabel}/><small>نام صرافی، Spot و /USDT در فهرست تکرار نمی‌شوند.</small></label>
        <label className="cs-field"><span>قیمت لحظه‌ای</span><div className="cs-live-price">{selectedMarket?.price?money(selectedMarket.price,8):"ناموجود"} <i>USDT</i></div></label>
        <label className="cs-field"><span>جهت معامله</span><div className="cs-segment"><button type="button" className={side==="long"?"active":""} onClick={()=>setSide("long")}>لانگ</button><button type="button" className={side==="short"?"active short":""} onClick={()=>setSide("short")} disabled={selectedMarket?.market_type!=="margin"}>شورت</button></div></label>
        <TargetField label="Entry" value={entry} onChange={setEntry} entry={entry} side={side}/>
        <label className="cs-field"><span>اهرم / ضریب</span><input inputMode="decimal" value={leverage} onChange={e=>setLeverage(e.target.value)}/><small>سقف بازار: {selectedMarket?("x"+trimNumber(selectedMarket.max_leverage,0)):"—"}</small></label>
      </div>
      <div className="cs-section-title">اهداف و حد ضرر</div>
      <div className="cs-target-grid"><TargetField label="TP1" value={tp1} onChange={setTp1} entry={entry} side={side}/><TargetField label="TP2" value={tp2} onChange={setTp2} entry={entry} side={side}/><TargetField label="TP3" value={tp3} onChange={setTp3} entry={entry} side={side}/><TargetField label="Stop Loss" value={sl} onChange={setSl} entry={entry} side={side}/></div>
      <div className="cs-fix-box"><div className="cs-fix-head"><ShieldCheck size={20}/><div><b>Fix Loss</b><span>محاسبه عدد پیشنهادی حجم بر اساس موجودی آزاد، فاصله SL و درصد ریسک</span></div></div><div className="cs-fix-grid"><label className="cs-field"><span>ریسک محاسباتی</span><div className="cs-input-suffix"><input value={risk} onChange={e=>setRisk(e.target.value)}/><i>٪</i></div></label><button type="button" className="cs-soft" onClick={calcFix}>محاسبه</button><div className="cs-fix-result"><span>حجم پیشنهادی</span><b>{fix?money(fix.suggested_notional):"—"} USDT</b><small>{fix?.capped_by_available_balance?"به موجودی/اهرم محدود شده":fix?"بر اساس فاصله حد ضرر":"ابتدا Entry و SL را وارد کنید"}</small></div></div></div>
      <div className="cs-form-grid compact"><label className="cs-field"><span>مبلغ ورود</span><div className="cs-input-suffix"><input value={capital} placeholder={fix?trimNumber(fix.suggested_notional,2):"مثلاً 50"} onChange={e=>setCapital(e.target.value)}/><i>USDT</i></div></label></div>
      <div className="cs-submit"><button type="button" className="cs-primary" disabled={saving} onClick={save}><ShieldCheck size={18}/>{saving?"در حال ثبت...":"بررسی و ساخت برنامه"}</button></div>
    </section>
    <section className="cs-panel cs-market-chart"><div className="cs-panel-head"><div><h2>{selectedMarket?marketLabel(selectedMarket):"بازار"}</h2><p>{accounts.find(x=>String(x.id)===account)?.exchange_name||""}</p></div><b className="cs-up">{selectedMarket?.price?money(selectedMarket.price,8):"—"}</b></div><SparkChart/><div className="cs-chart-note">نمودار سبک برای پایش سریع؛ داده قیمت از feed همان بازار خوانده می‌شود.</div></section>
  </div>;
}

function SmartPage() {
  const [text,setText]=useState(""),[result,setResult]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const run=async()=>{setBusy(true);setError("");try{const data=await request("api/v1/smart-paste/",{method:"POST",body:{text}});setResult(data.signal);}catch(e){setError(e.message);}finally{setBusy(false);}};
  return <div className="cs-grid-two"><section className="cs-panel"><div className="cs-panel-head"><div><h2>Smart Paste</h2><p>متن سیگنال را بدون تغییر وارد کنید؛ Parser آن را ساختارمند می‌کند.</p></div><Sparkles size={20}/></div><textarea className="cs-signal-text" value={text} onChange={e=>setText(e.target.value)} placeholder="BTC/USDT LONG ..."/>{error&&<div className="cs-inline-error">{error}</div>}<div className="cs-submit"><button className="cs-primary" onClick={run} disabled={!text.trim()||busy}><Sparkles size={18}/>{busy?"در حال تحلیل...":"تحلیل سیگنال"}</button></div></section><section className="cs-panel"><div className="cs-panel-head"><div><h2>نتیجه تحلیل</h2><p>پیش از تأیید نهایی باید بازبینی انسانی انجام شود.</p></div></div>{result?<div className="cs-analysis"><Info label="وضعیت" value={result.status}/><Info label="جهت" value={result.structured?.side||"—"}/><Info label="Entry" value={result.structured?.entry||"—"}/><Info label="Stop" value={result.structured?.stop_loss||"—"}/><a className="cs-primary" href={api("inbox/"+result.id+"/")}>بازبینی سیگنال</a></div>:<Empty>پس از تحلیل، خروجی ساختارمند اینجا نمایش داده می‌شود.</Empty>}</section></div>;
}
function Info({label,value}){return <div className="cs-info"><span>{label}</span><b>{String(value)}</b></div>}

function InboxPage() {
  const [data,setData]=useState(null),[filter,setFilter]=useState("");
  useEffect(()=>{request("api/v1/inbox/").then(setData).catch(()=>setData({items:[]}));},[]);
  if(!data)return <Loading/>;
  const rows=(data.items||[]).filter(x=>!filter||x.raw_text?.toLowerCase().includes(filter.toLowerCase())||String(x.status).includes(filter));
  return <div className="cs-page"><div className="cs-page-head"><div><h1>صندوق سیگنال‌ها</h1><p>ورودی دستی، Smart Paste و Telegram در یک فهرست.</p></div><a className="cs-primary" href={api("smart-paste/")}><Sparkles size={18}/> تحلیل سیگنال</a></div><section className="cs-panel"><div className="cs-toolbar"><input placeholder="جست‌وجوی متن یا وضعیت..." value={filter} onChange={e=>setFilter(e.target.value)}/></div><div className="cs-signal-cards">{rows.map(x=><a href={api("inbox/"+x.id+"/")} key={x.id} className="cs-signal-card"><div><span className="cs-status ok">{x.source_method}</span><b>سیگنال #{x.id}</b></div><p>{x.raw_text||"بدون متن"}</p><div><span>{x.structured?.side||"—"}</span><strong>{x.structured?.entry?money(x.structured.entry,8):"نیازمند بازبینی"}</strong></div><MiniSignalChart seed={x.id}/></a>)}</div></section></div>;
}
function MiniSignalChart({seed}){const y=20+(seed%4)*7;return <svg className="cs-mini-chart" viewBox="0 0 220 60" preserveAspectRatio="none"><path d={"M0 48 L32 "+(44-y/8)+" L70 42 L104 "+(30+y/10)+" L140 32 L178 "+(18+y/12)+" L220 12"} fill="none" stroke="#20a66a" strokeWidth="3"/></svg>}

function SignalDetailPage() {
  const node=document.getElementById("cs-signal-detail-root"), id=node?.dataset.signalId;
  const [item,setItem]=useState(null),[accounts,setAccounts]=useState([]),[markets,setMarkets]=useState([]),[form,setForm]=useState({account_id:"",market_id:"",side:"long",entry_price:"",stop_loss:"",tp1:"",tp2:"",tp3:"",reason:""});
  const [message,setMessage]=useState("");
  useEffect(()=>{Promise.all([request("api/v1/inbox/"+id+"/"),request("api/v1/exchanges/")]).then(([d,e])=>{const s=d.signal;setItem(s);setAccounts((e.accounts||[]).filter(x=>x.environment==="live"&&!["binance","simulator"].includes(String(x.exchange_code||x.exchange||"").toLowerCase())));const st=s.structured||{};setForm(f=>({...f,account_id:String(st.account_id||""),market_id:String(st.market_id||""),side:st.side||"long",entry_price:st.entry||"",stop_loss:st.stop_loss||"",tp1:st.targets?.[0]?.price||"",tp2:st.targets?.[1]?.price||"",tp3:st.targets?.[2]?.price||""}));}).catch(e=>setMessage(e.message));},[id]);
  useEffect(()=>{if(!form.account_id)return;request("api/v1/manual/markets/?account="+form.account_id).then(d=>setMarkets(d.markets||[])).catch(()=>setMarkets([]));},[form.account_id]);
  const change=(k,v)=>setForm(f=>({...f,[k]:v}));
  const save=async()=>{try{const d=await request("api/v1/inbox/"+id+"/edit/",{method:"POST",body:{...form,account_id:Number(form.account_id),market_id:Number(form.market_id),revision:item.revision}});setItem(d.signal);setMessage("ویرایش ثبت شد.");}catch(e){setMessage(e.message);}};
  const action=async(action)=>{try{const d=await request("api/v1/inbox/"+id+"/action/",{method:"POST",body:{revision:item.revision,action,reason:action==="reject"?form.reason:""}});setItem(d.signal);setMessage(action==="reject"?"سیگنال رد شد.":"سیگنال تأیید شد.");}catch(e){setMessage(e.message);}};
  if(!item)return <Loading/>;
  const editable=["new","parsed","needs_review"].includes(item.status);
  return <div className="cs-grid-two"><section className="cs-panel"><div className="cs-panel-head"><div><h2>متن اصلی</h2><p>نسخه ذخیره‌شده بدون تغییر</p></div><span className="cs-status ok">{item.status}</span></div><pre className="cs-raw">{item.raw?.original_text}</pre></section><section className="cs-panel"><div className="cs-panel-head"><div><h2>بازبینی سیگنال</h2><p>دلیل ویرایش اجباری است؛ علت رد اختیاری.</p></div></div>{message&&<div className="cs-inline-note">{message}</div>}<div className="cs-form-grid">
    <label className="cs-field"><span>حساب صرافی</span><SearchSelect items={accounts} value={form.account_id} onChange={v=>{change("account_id",v);change("market_id","");}} renderLabel={x=>(x.exchange_name||x.exchange||"")+" · "+x.label}/></label>
    <label className="cs-field"><span>بازار</span><SearchSelect items={markets} value={form.market_id} onChange={v=>change("market_id",v)} renderLabel={m=>m.asset+(m.market_type==="margin"&&Number(m.max_leverage)>1?" x"+trimNumber(m.max_leverage,0):"")}/></label>
    <label className="cs-field"><span>جهت</span><select value={form.side} onChange={e=>change("side",e.target.value)}><option value="long">Long</option><option value="short">Short</option></select></label>
    <TargetField label="Entry" value={form.entry_price} onChange={v=>change("entry_price",v)} entry={form.entry_price} side={form.side}/>
    <TargetField label="TP1" value={form.tp1} onChange={v=>change("tp1",v)} entry={form.entry_price} side={form.side}/>
    <TargetField label="TP2" value={form.tp2} onChange={v=>change("tp2",v)} entry={form.entry_price} side={form.side}/>
    <TargetField label="TP3" value={form.tp3} onChange={v=>change("tp3",v)} entry={form.entry_price} side={form.side}/>
    <TargetField label="Stop Loss" value={form.stop_loss} onChange={v=>change("stop_loss",v)} entry={form.entry_price} side={form.side}/>
    <label className="cs-field cs-wide"><span>دلیل ویرایش</span><input value={form.reason} onChange={e=>change("reason",e.target.value)} placeholder="برای ثبت هر ویرایش حداقل ۳ حرف"/></label>
  </div>{editable&&<div className="cs-submit split"><button className="cs-soft" onClick={()=>action("reject")}>رد سیگنال</button><button className="cs-soft" onClick={save} disabled={form.reason.trim().length<3}>ثبت ویرایش</button><button className="cs-primary" onClick={()=>action("approve")} disabled={item.status!=="parsed"}>تأیید سیگنال</button></div>}</section></div>;
}

mount("cs-manual-root", ManualPage);
mount("cs-smart-root", SmartPage);
mount("cs-inbox-root", InboxPage);
mount("cs-signal-detail-root", SignalDetailPage);


function ExchangeGuide({guides,onClose}) {
  const [active,setActive]=useState(guides[0]?.code||"");
  const guide=guides.find(x=>x.code===active);
  return <div className="cs-modal-backdrop" onClick={onClose}><div className="cs-modal cs-guide-modal" onClick={e=>e.stopPropagation()}><div className="cs-modal-head"><div><h2>راهنمای اتصال حساب‌های صرافی</h2><p>برای هر حساب یک API مستقل بسازید و برداشت را فعال نکنید.</p></div><button className="cs-icon" onClick={onClose}><X size={18}/></button></div><div className="cs-guide-tabs">{guides.map(g=><button className={active===g.code?"active":""} key={g.code} onClick={()=>setActive(g.code)}>{g.name}</button>)}</div>{guide&&<div className="cs-guide-body"><div className="cs-guide-fields">اطلاعات لازم: <b>{guide.credential_fields.join(" + ")}</b></div><ol>{guide.steps.map((s,i)=><li key={i}>{s}</li>)}</ol><div className="cs-guide-note"><ShieldCheck size={18}/><span>کلید API در مرورگر دوباره نمایش داده نمی‌شود؛ لاگ اتصال فقط مرحله و کد خطا را نگه می‌دارد.</span></div></div>}</div></div>;
}
function AddExchange({catalog,guides,onDone,onClose}) {
  const [form,setForm]=useState({exchange:catalog[0]?.code||"",label:"حساب اصلی",api_key:"",api_secret:"",passphrase:"",no_withdrawal_confirmed:false,ip_restricted_confirmed:false});
  const [error,setError]=useState(""),[busy,setBusy]=useState(false),[showGuide,setShowGuide]=useState(false);
  const set=(k,v)=>setForm(f=>({...f,[k]:v}));
  const submit=async()=>{setBusy(true);setError("");try{await request("api/v1/exchange-accounts/",{method:"POST",body:form});onDone();}catch(e){setError(e.payload?.errors?JSON.stringify(e.payload.errors):e.message);}finally{setBusy(false);}};
  return <div className="cs-modal-backdrop" onClick={onClose}><div className="cs-modal" onClick={e=>e.stopPropagation()}><div className="cs-modal-head"><div><h2>افزودن حساب صرافی</h2><p>فقط حساب اصلی؛ Demo و Paper در این رابط وجود ندارد.</p></div><button className="cs-icon" onClick={onClose}><X size={18}/></button></div>{error&&<div className="cs-inline-error">{error}</div>}<div className="cs-form-grid">
    <label className="cs-field"><span>صرافی</span><select value={form.exchange} onChange={e=>set("exchange",e.target.value)}>{catalog.map(x=><option key={x.code} value={x.code}>{x.name}</option>)}</select></label>
    <label className="cs-field"><span>نام اتصال</span><input value={form.label} onChange={e=>set("label",e.target.value)}/></label>
    <label className="cs-field cs-wide"><span>API Key / Token</span><input autoComplete="off" value={form.api_key} onChange={e=>set("api_key",e.target.value)}/></label>
    {form.exchange!=="nobitex"&&<label className="cs-field cs-wide"><span>API Secret</span><input type="password" autoComplete="new-password" value={form.api_secret} onChange={e=>set("api_secret",e.target.value)}/></label>}
    {form.exchange==="weex"&&<label className="cs-field cs-wide"><span>Passphrase</span><input type="password" value={form.passphrase} onChange={e=>set("passphrase",e.target.value)}/></label>}
    <label className="cs-check cs-wide"><input type="checkbox" checked={form.no_withdrawal_confirmed} onChange={e=>set("no_withdrawal_confirmed",e.target.checked)}/><span>تأیید می‌کنم مجوز برداشت این API خاموش است.</span></label>
    <label className="cs-check cs-wide"><input type="checkbox" checked={form.ip_restricted_confirmed} onChange={e=>set("ip_restricted_confirmed",e.target.checked)}/><span>IP سرور را محدود کرده‌ام (در صورت پشتیبانی صرافی).</span></label>
  </div><div className="cs-modal-actions"><button className="cs-soft" onClick={()=>setShowGuide(true)}>راهنمای اتصال</button><button className="cs-primary" disabled={busy||!form.no_withdrawal_confirmed} onClick={submit}>{busy?"در حال ثبت...":"ثبت و بررسی اتصال"}</button></div>{showGuide&&<ExchangeGuide guides={guides} onClose={()=>setShowGuide(false)}/>}</div></div>;
}
function ExchangesPage() {
  const [data,setData]=useState(null),[guides,setGuides]=useState([]),[adding,setAdding]=useState(false),[showGuide,setShowGuide]=useState(false),[error,setError]=useState("");
  const load=()=>Promise.all([request("api/v1/exchanges/"),request("api/v1/exchange-guides/")]).then(([d,g])=>{setData(d);setGuides(g.items||[]);}).catch(e=>setError(e.message));
  useEffect(()=>{load();},[]);
  const sync=async(id)=>{try{await request("api/v1/exchange-accounts/"+id+"/sync/",{method:"POST"});await load();}catch(e){setError(e.message);}};
  if(!data)return <Loading/>;
  return <div className="cs-page"><div className="cs-page-head"><div><h1>حساب‌های صرافی</h1><p>همه اتصال‌های اصلی در یک جدول؛ وضعیت Worker و API قابل پیگیری است.</p></div><div className="cs-actions"><button className="cs-soft" onClick={()=>setShowGuide(true)}>راهنمای اتصال همه صرافی‌ها</button><button className="cs-primary" onClick={()=>setAdding(true)}><PlusCircle size={18}/> افزودن حساب</button></div></div>{error&&<div className="cs-inline-error">{error}</div>}<section className="cs-panel"><div className="cs-table-wrap"><table><thead><tr><th>صرافی</th><th>نام حساب</th><th>وضعیت API</th><th>آخرین بررسی</th><th>آخرین مرحله</th><th></th></tr></thead><tbody>{data.accounts.map(a=><tr key={a.id}><td><b>{a.exchange_name||a.exchange}</b></td><td>{a.label}</td><td><Status value={a.status}/></td><td>{a.last_sync_at?new Date(a.last_sync_at).toLocaleString("fa-IR"):"هنوز بررسی نشده"}</td><td>{a.latest_connection_log?<span className={"cs-log-inline "+a.latest_connection_log.status}>{a.latest_connection_log.stage} · {a.latest_connection_log.message}</span>:"—"}</td><td><div className="cs-row-actions"><a className="cs-soft" href={api("exchanges/"+a.id+"/")}>جزئیات</a><button className="cs-soft" onClick={()=>sync(a.id)}>بررسی مجدد</button></div></td></tr>)}</tbody></table></div>{!data.accounts.length&&<Empty>هنوز حسابی متصل نشده است.</Empty>}</section>{adding&&<AddExchange catalog={data.exchanges} guides={guides} onClose={()=>setAdding(false)} onDone={()=>{setAdding(false);load();}}/>}{showGuide&&<ExchangeGuide guides={guides} onClose={()=>setShowGuide(false)}/>}</div>;
}
function ExchangeDetailPage() {
  const id=document.getElementById("cs-exchange-detail-root")?.dataset.accountId;
  const [account,setAccount]=useState(null),[logs,setLogs]=useState([]),[dash,setDash]=useState(null),[error,setError]=useState("");
  const load=()=>Promise.all([request("api/v1/exchange-accounts/"+id+"/"),request("api/v1/exchange-accounts/"+id+"/logs/"),request("api/v1/dashboard/?account="+id)]).then(([a,l,d])=>{setAccount(a.account);setLogs(l.items||[]);setDash(d);}).catch(e=>setError(e.message));
  useEffect(()=>{load();},[id]);
  const sync=async()=>{await request("api/v1/exchange-accounts/"+id+"/sync/",{method:"POST"});setTimeout(load,700);};
  if(!account)return <Loading/>;
  const card=dash?.accounts?.[0]; const balances=[...(card?.balances||[])].sort((a,b)=>(a.asset==="USDT"?-1:b.asset==="USDT"?1:a.asset.localeCompare(b.asset)));
  return <div className="cs-page"><div className="cs-page-head"><div><h1>{account.exchange_name}</h1><p>{account.label} · آخرین بررسی {account.last_sync_at?new Date(account.last_sync_at).toLocaleString("fa-IR"):"—"}</p></div><div className="cs-actions"><button className="cs-soft" onClick={sync}>بررسی اتصال</button><form method="post" action={api("exchanges/"+id+"/delete/")}><input type="hidden" name="csrfmiddlewaretoken" value={csrfToken()}/><button className="cs-danger-button" type="submit">حذف اتصال</button></form></div></div>{error&&<div className="cs-inline-error">{error}</div>}<div className="cs-grid-two"><section className="cs-panel"><div className="cs-panel-head"><div><h2>آخرین موجودی</h2><p>USDT همیشه در ابتدای فهرست قرار می‌گیرد.</p></div><Status value={account.status}/></div><div className="cs-balance-list">{balances.map((b,i)=><div className={"cs-balance-row "+(b.asset==="USDT"?"primary":"")} key={i}><div><b>{b.asset}</b><span>{b.wallet==="margin"?"Margin":"Spot"}</span></div><div><strong>{money(b.free,Math.abs(Number(b.free))<1?8:2)}</strong><small>آزاد</small></div><div><strong>{money(b.locked,Math.abs(Number(b.locked))<1?8:2)}</strong><small>قفل</small></div></div>)}</div></section><section className="cs-panel"><div className="cs-panel-head"><div><h2>لاگ اتصال</h2><p>مرحله دقیق بررسی بدون ثبت Secret یا API Key</p></div></div><div className="cs-log-list">{logs.map((l,i)=><div key={i}><span className={"cs-log-dot "+l.status}/><div><b>{l.stage}</b><p>{l.message}</p><small>{l.code?l.code+" · ":""}{new Date(l.created_at).toLocaleString("fa-IR")}</small></div></div>)}</div></section></div><section className="cs-panel"><div className="cs-panel-head"><div><h2>دسترسی‌های گزارش‌شده</h2><p>برای تشخیص سریع مشکل اتصال</p></div></div><div className="cs-permissions"><Info label="Read" value={account.permissions?.can_read?"فعال":"غیرفعال"}/><Info label="Spot" value={account.permissions?.can_trade_spot?"فعال":"غیرفعال"}/><Info label="Margin" value={account.permissions?.can_trade_margin?"فعال":"غیرفعال"}/><Info label="Withdrawal" value={account.permissions?.can_withdraw===false?"خاموش":"نیازمند بررسی"}/></div></section></div>;
}
mount("cs-exchanges-root", ExchangesPage);
mount("cs-exchange-detail-root", ExchangeDetailPage);
