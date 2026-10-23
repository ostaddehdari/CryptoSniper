import React, {useEffect, useMemo, useState} from "react";
import { createRoot } from "react-dom/client";
import {
  LayoutDashboard, WalletCards, ArrowLeftRight, PlusCircle, Sparkles, Radar, Bell,
  Settings, ChevronRight, ChevronLeft, Search, Eye, EyeOff, RefreshCw, TrendingUp,
  CircleDollarSign, PlugZap, Trash2, MessageCircle, Copy, Star, GripVertical,
  ShieldCheck, Activity, SlidersHorizontal, MoreHorizontal, X, CheckCircle2,
  AlertTriangle, LogOut, UserCircle2, ChartCandlestick, ClipboardPaste, Inbox,
  BarChart3, ServerCog, Save, KeyRound, Link2, ExternalLink, Send, LoaderCircle
} from "lucide-react";
import "./styles.css";
import "./stage26.css";
import "./stage27.css";

const BASE = (window.__CS_BASE__ || "/cryptosniper").replace(/\/$/, "");
const fmt=(v,d=2)=>Number(v||0).toLocaleString("fa-IR",{minimumFractionDigits:d,maximumFractionDigits:d});
const dt=v=>v?new Date(v).toLocaleString("fa-IR"):"—";
const num=v=>{const n=Number(v);return Number.isFinite(n)?n:0};
const statusFa={connected:"متصل",restricted:"محدود",pending:"در انتظار",error:"خطا",disabled:"غیرفعال",open:"باز",filled:"تکمیل",partial:"بخشی",cancelled:"لغو",failed:"ناموفق",uncertain:"نامعلوم",submitting:"در حال ارسال",new:"جدید",parsed:"تحلیل‌شده",needs_review:"نیازمند بررسی",approved:"تأییدشده",rejected:"ردشده",complete:"کامل",running:"در حال اجرا",paused:"متوقف",completed:"کامل",pending_entry:"منتظر تکمیل ورود",active:"فعال",exiting:"در حال خروج",closed:"بسته",waiting:"منتظر",exit_pending:"خروج در صف",skipped:"عبور شد"};

function cookie(name){
  return document.cookie.split(";").map(v=>v.trim()).find(v=>v.startsWith(name+"="))?.slice(name.length+1)||"";
}
async function api(path, opts={}){
  const method=opts.method||"GET";
  const headers={Accept:"application/json",...(opts.headers||{})};
  let body=opts.body;
  if(body && typeof body!=="string" && !(body instanceof FormData)){
    headers["Content-Type"]="application/json"; body=JSON.stringify(body);
  }
  if(!["GET","HEAD"].includes(method.toUpperCase())) headers["X-CSRFToken"]=decodeURIComponent(cookie("cryptosniper_csrftoken"));
  const res=await fetch(BASE+path,{credentials:"same-origin",...opts,method,headers,body});
  let data={}; try{data=await res.json()}catch{}
  if(res.status===401){location.href=BASE+"/auth/login/";throw new Error("authentication_required")}
  if(!res.ok){const e=new Error(data.error?.[0]||data.error||Object.values(data.errors||{})?.[0]?.[0]?.message||"خطای درخواست");e.status=res.status;e.data=data;throw e}
  return data;
}
function useHashPage(){
  const get=()=>location.hash.replace(/^#\/?/,"").split("?")[0]||"dashboard";
  const [page,setState]=useState(get);
  useEffect(()=>{const fn=()=>setState(get());addEventListener("hashchange",fn);return()=>removeEventListener("hashchange",fn)},[]);
  const setPage=p=>{location.hash="#/"+p;setState(p)};
  return [page,setPage];
}

function App(){
  const [collapsed,setCollapsed]=useState(localStorage.getItem("cs_sidebar_collapsed")==="1");
  const [page,setPage]=useHashPage();
  const [boot,setBoot]=useState(null); const [loading,setLoading]=useState(true); const [error,setError]=useState("");
  const [decimals,setDecimals]=useState(Number(localStorage.getItem("cs_decimals")||2));
  const [toast,setToast]=useState("");
  const [stepUp,setStepUp]=useState(false);
  const [stepUpAction,setStepUpAction]=useState(null);
  const [manualSeed,setManualSeed]=useState(null);
  const refresh=async()=>{try{setError("");const b=await api("/api/v1/ui/bootstrap/");setBoot(b)}catch(e){setError(e.message)}finally{setLoading(false)}};
  useEffect(()=>{refresh();const t=setInterval(refresh,10000);return()=>clearInterval(t)},[]);
  const notify=m=>{setToast(m);setTimeout(()=>setToast(""),3500)};
  const toggle=()=>{const v=!collapsed;setCollapsed(v);localStorage.setItem("cs_sidebar_collapsed",v?"1":"0")};
  const updateDecimals=v=>{setDecimals(v);localStorage.setItem("cs_decimals",String(v))};
  const menu=[
    ["dashboard","نمای کلی",LayoutDashboard],
    ["trades","معاملات",ArrowLeftRight],
    ["inbox","صندوق سیگنال",Inbox],
    ["exchanges","صرافی‌ها",PlugZap],
    ["telegram","تلگرام و سیگنال‌ها",MessageCircle],
    ["alerts","هشدارها",Bell],
    ["reports","گزارش‌ها",BarChart3],
    ["operations","وضعیت سیستم",ServerCog],
    ["settings","تنظیمات",Settings],
  ];
  const title=menu.find(x=>x[0]===page)?.[1]||"CryptoSniper";
  if(loading) return <FullLoading/>;
  return <div className="app">
    <aside className={"sidebar "+(collapsed?"collapsed":"")}>
      <div className="brand"><div className="logoMark"><ChartCandlestick size={21}/></div>{!collapsed&&<div><strong>CryptoSniper</strong><span>مرکز کنترل معاملات واقعی</span></div>}</div>
      <button className="collapseBtn" onClick={toggle}>{collapsed?<ChevronLeft size={18}/>:<ChevronRight size={18}/>}</button>
      <nav>{menu.map(([id,label,Icon])=><button key={id} className={"navItem "+(page===id?"active":"")} onClick={()=>setPage(id)} title={label}><Icon size={19}/>{!collapsed&&<span>{label}</span>}</button>)}</nav>
      <div className="sidebarFoot"><button className="navItem" onClick={()=>setPage("settings")}><UserCircle2 size={19}/>{!collapsed&&<span>{boot?.user?.name||"حساب کاربری"}</span>}</button><a className="navItem dangerLite" href={BASE+"/auth/logout/"}><LogOut size={19}/>{!collapsed&&<span>خروج</span>}</a></div>
    </aside>
    <main className={"main "+(collapsed?"wide":"")}>
      <header className="topbar"><div><h1>{page==="newtrade"?"معامله جدید":title}</h1><p>{page==="dashboard"?"همه حساب‌ها، معاملات، سیگنال‌ها و هشدارها در یک نما":"CryptoSniper · حساب واقعی"}</p></div><LivePriceStrip/><div className="topActions"><button type="button" className="iconBtn notification" onClick={()=>setPage("alerts")}><Bell size={19}/>{boot?.unread_notifications>0&&<span className="badge">{boot.unread_notifications}</span>}</button><button type="button" className="primary" onClick={()=>setPage("newtrade")}><PlusCircle size={18}/> معامله جدید</button></div></header>
      <section className="content">
        {error&&<ErrorBox text={error}/>} 
        {page==="dashboard"&&<Dashboard boot={boot} decimals={decimals} refreshBoot={refresh} setPage={setPage}/>} 
        {page==="trades"&&<Trades decimals={decimals} notify={notify} setPage={setPage} requestStepUp={action=>{setStepUpAction(()=>action||null);setStepUp(true)}}/>} 
        {page==="newtrade"&&<NewTrade boot={boot} decimals={decimals} notify={notify} requestStepUp={action=>{setStepUpAction(()=>action||null);setStepUp(true)}} seed={manualSeed} setManualSeed={setManualSeed}/>} 
        {page==="inbox"&&<SignalInbox notify={notify} boot={boot} setPage={setPage} setManualSeed={setManualSeed}/>} 
        {page==="exchanges"&&<Exchanges boot={boot} refreshBoot={refresh} notify={notify} requestStepUp={action=>{setStepUpAction(()=>action||null);setStepUp(true)}}/>} 
        {page==="telegram"&&<Telegram notify={notify} setPage={setPage} setManualSeed={setManualSeed} requestStepUp={()=>setStepUp(true)}/>} 
        {page==="alerts"&&<Alerts notify={notify}/>} 
        {page==="reports"&&<Reports decimals={decimals}/>} 
        {page==="operations"&&<Operations notify={notify}/>} 
        {page==="settings"&&<SettingsPage decimals={decimals} setDecimals={updateDecimals} notify={notify}/>} 
      </section>
    </main>
    {toast&&<div className="toast">{toast}</div>}
    {stepUp&&<StepUpModal onClose={()=>{setStepUp(false);setStepUpAction(null)}} onSuccess={async()=>{const action=stepUpAction;setStepUp(false);setStepUpAction(null);if(action)await action()}} notify={notify}/>} 
  </div>
}
function FullLoading(){return <div className="fullLoading"><LoaderCircle className="spin"/><b>در حال بارگذاری CryptoSniper…</b></div>}
function ErrorBox({text}){return <div className="errorBox"><AlertTriangle size={18}/><span>{text}</span></div>}
function Metric({icon:Icon,label,value,hint,positive}){return <div className="metric card"><div className="metricTop"><div className="metricIcon"><Icon size={20}/></div><span>{label}</span></div><strong className={positive?"up":""}>{value}</strong><small>{hint}</small></div>}
function Status({value}){const cls=value==="connected"||value==="approved"||value==="filled"||value==="open"?"ok":value==="error"||value==="failed"||value==="rejected"?"danger":"warn";return <span className={"status "+cls}>{statusFa[value]||value||"—"}</span>}
function Empty({text="داده‌ای برای نمایش وجود ندارد."}){return <div className="emptyState">{text}</div>}
function LivePriceStrip(){
  const [prices,setPrices]=useState({});
  useEffect(()=>{
    let stopped=false;
    const run=()=>api("/api/v1/markets/public-prices/").then(d=>{if(!stopped)setPrices(d.prices||{})}).catch(()=>{});
    run();
    const timer=setInterval(run,2000);
    return()=>{stopped=true;clearInterval(timer)}
  },[]);
  const item=(label,row,suffix)=><div className={"liveTicker "+(row?.stale?"stale":"")}><span className="liveDot"/><div><small>{label}</small><b>{row?.price?fmt(row.price,num(row.price)<10?4:2):"ناموجود"} {suffix}</b><em>{row?.source?row.source.toUpperCase():"—"}{row?.age_seconds!=null?" · "+row.age_seconds+"s":""}</em></div></div>;
  const usdtRow=prices.usdt_irt?{...prices.usdt_irt,price:prices.usdt_irt.display_price_toman||prices.usdt_irt.price}:prices.usdt_irt;
  return <div className="livePriceStrip">{item("BTC / USDT",prices.btc_usdt,"USDT")}{item("USDT / تومان",usdtRow,"تومان")}</div>
}

function Dashboard({boot,decimals,refreshBoot,setPage}){
  const [extra,setExtra]=useState({orders:[],external:[],signals:[],alerts:[],notifications:[],report:null});
  const [showAll,setShowAll]=useState(false);
  const load=async()=>{
    const [t,s,a,n,r]=await Promise.allSettled([
      api("/api/v1/live-orders/"),
      api("/api/v1/inbox/"),
      api("/api/v1/alerts/"),
      api("/api/v1/notifications/"),
      api("/api/v1/reports/?period=month&group=total")
    ]);
    setExtra({
      orders:t.value?.orders||[],
      external:t.value?.external||[],
      signals:s.value?.items||[],
      alerts:a.value?.alerts||[],
      notifications:n.value?.items||[],
      report:r.value||null
    });
  };
  useEffect(()=>{load();const t=setInterval(load,10000);return()=>clearInterval(t)},[]);
  const accounts=boot?.accounts||[];
  const usdt=accounts.reduce((sum,a)=>sum+(a.balances||[]).filter(b=>b.asset==="USDT").reduce((x,b)=>x+num(b.free),0),0);
  const total=accounts.reduce((sum,a)=>sum+num(a.known_valuation),0);
  const incompleteValuation=accounts.some(a=>a.valuation_complete===false);
  const openOrders=extra.orders.filter(x=>["open","partial","pending","submitting"].includes(x.state));
  const net=(extra.report?.rows||[]).reduce((s,r)=>s+num(r.net_realized),0);
  return <>
    <div className="metricGrid">
      <button type="button" className="metric card metricButton" onClick={()=>setPage("exchanges")}><div className="metricTop"><div className="metricIcon"><WalletCards size={20}/></div><span>ارزش کل دارایی‌ها</span></div><strong>{fmt(total,decimals)} USDT</strong><small>{incompleteValuation?"فقط دارایی‌های دارای قیمت تازه":"ارزش‌گذاری با قیمت تازه همان صرافی"}</small></button>
      <button type="button" className="metric card metricButton" onClick={()=>setPage("exchanges")}><div className="metricTop"><div className="metricIcon"><CircleDollarSign size={20}/></div><span>تتر آزاد لحظه‌ای</span></div><strong>{fmt(usdt,decimals)} USDT</strong><small>جمع USDT آزاد حساب‌ها</small></button>
      <button type="button" className="metric card metricButton" onClick={()=>setPage("exchanges")}><div className="metricTop"><div className="metricIcon"><PlugZap size={20}/></div><span>حساب‌های متصل</span></div><strong>{accounts.filter(a=>a.status==="connected").length}</strong><small>{accounts.length} حساب قابل نمایش</small></button>
      <button type="button" className="metric card metricButton" onClick={()=>setPage("trades")}><div className="metricTop"><div className="metricIcon"><ArrowLeftRight size={20}/></div><span>سفارش‌های واقعی</span></div><strong>{openOrders.length}</strong><small>برای مشاهده معاملات باز کلیک کنید</small></button>
      <button type="button" className="metric card metricButton" onClick={()=>setPage("reports")}><div className="metricTop"><div className="metricIcon"><TrendingUp size={20}/></div><span>سود خالص ماهانه</span></div><strong className={net>=0?"up":"down"}>{net>=0?"+":""}{fmt(net,decimals)} USDT</strong><small>بر اساس گزارش تحقق‌یافته</small></button>
    </div>
    <div className="grid2">
      <div className="card">
        <div className="cardHead"><div><h3>حساب‌ها و موجودی</h3><p>داده زنده‌ی حساب‌های متصل</p></div><div className="row gap"><button type="button" className="softBtn" onClick={()=>setShowAll(!showAll)}>{showAll?<EyeOff size={17}/>:<Eye size={17}/>} {showAll?"فقط USDT":"تمام موجودی‌ها"}</button><button type="button" className="iconBtn" onClick={()=>{refreshBoot();load()}}><RefreshCw size={17}/></button></div></div>
        <div className="tableScroll"><table><thead><tr><th>صرافی</th><th>USDT آزاد</th>{showAll&&<th>سایر موجودی‌ها</th>}<th>وضعیت</th><th></th></tr></thead><tbody>{accounts.map(a=>{const u=(a.balances||[]).find(b=>b.asset==="USDT");return <tr key={a.id}><td><div className="exchangeName"><span className="exchangeLogo">{a.exchange_name?.[0]||a.exchange[0]}</span><div><b>{a.exchange_name}</b><small>{a.label}</small></div></div></td><td className="usdtHighlight">{fmt(u?.free||0,decimals)} USDT</td>{showAll&&<td><div className="chips">{(a.balances||[]).filter(b=>b.asset!=="USDT"&&num(b.total)>0).slice(0,8).map(b=><span className="pill" key={b.asset}>{b.asset}: {fmt(b.total,decimals)}</span>)}</div></td>}<td><Status value={a.status}/></td><td><button type="button" className="linkBtn" onClick={()=>setPage("exchanges")}>جزئیات</button></td></tr>})}</tbody></table></div>
      </div>
      <div className="card">
        <div className="cardHead"><div><h3>وضعیت حساب‌ها</h3><p>آخرین همگام‌سازی و سلامت اتصال</p></div></div>
        <div className="accountHealth">{accounts.map(a=><div className="healthRow" key={a.id}><div><b>{a.exchange_name}</b><span>{a.last_error_message||"بدون خطای ثبت‌شده"}</span></div><div><Status value={a.status}/><small>{dt(a.last_sync_at)}</small></div></div>)}</div>
      </div>
    </div>
    <DashboardTabs extra={extra} decimals={decimals} setPage={setPage}/>
  </>
}

function DashboardTabs({extra,decimals,setPage}){
  const [tab,setTab]=useState("trades");
  const body=tab==="trades"
    ? <TradesTable rows={extra.orders.slice(0,8)} decimals={decimals} onSelect={()=>setPage("trades")}/>
    : tab==="signals"
      ? <div className="signalChartGrid">{extra.signals.slice(0,6).map(s=><SignalMiniChart key={s.id} signal={s} onOpen={()=>setPage("inbox")}/>)}</div>
      : tab==="alerts"
        ? <div className="simpleList">{extra.alerts.slice(0,8).map(x=><button type="button" key={x.id} className="dashboardListButton" onClick={()=>setPage("alerts")}><div><b>{x.title}</b><span>{x.market_symbol||"—"} · {x.kind} · {x.threshold}</span></div></button>)}{!extra.alerts.length&&<Empty text="هشدار فعالی وجود ندارد."/>}</div>
        : <div className="simpleList">{extra.notifications.slice(0,8).map(x=><button type="button" key={x.id} className="dashboardListButton" onClick={()=>setPage("alerts")}><div><b>{x.title}</b><span>{x.body}</span></div></button>)}{!extra.notifications.length&&<Empty text="اعلانی وجود ندارد."/>}</div>;
  return <div className="card dashboardBottom" id="dashboard-latest">
    <div className="tabs">{[["trades","آخرین معاملات"],["signals","آخرین سیگنال‌ها"],["alerts","آخرین هشدارها"],["notifications","اعلان‌ها"]].map(([id,l])=><button type="button" className={tab===id?"active":""} onClick={e=>{e.preventDefault();setTab(id);requestAnimationFrame(()=>document.getElementById("dashboard-latest")?.scrollIntoView({behavior:"smooth",block:"nearest"}))}} key={id}>{l}</button>)}</div>
    {body}
  </div>
}

function isExternalComplete(item){
  const s=String(item?.status||"").toLowerCase();
  return item?.kind==="fill"||["filled","done","completed","closed","2"].includes(s);
}
function Trades({decimals,notify,setPage,requestStepUp}){
  const [data,setData]=useState({orders:[],external:[]});
  const [filter,setFilter]=useState("open");
  const [externalFilter,setExternalFilter]=useState("all");
  const [selected,setSelected]=useState(null);
  const load=()=>api("/api/v1/live-orders/").then(setData).catch(e=>notify(e.message));
  useEffect(()=>{load();const t=setInterval(load,5000);return()=>clearInterval(t)},[]);
  const activeStates=["open","partial","pending","submitting","uncertain"];
  const managementOpenStates=["pending_entry","active","paused","exiting","error"];
  const internalEntries=(data.orders||[]).filter(x=>!["managed_tp_exit","managed_stop_exit"].includes(x.role));
  const rows=internalEntries.filter(x=>{
    const managed=x.management;
    if(filter==="all")return true;
    if(filter==="open")return activeStates.includes(x.state)||managementOpenStates.includes(managed?.state);
    if(filter==="filled")return managed?managed.state==="closed":x.state==="filled";
    if(filter==="failed")return x.state==="failed"||managed?.state==="error";
    return x.state===filter;
  });
  const externalRows=(data.external||[]).filter(x=>externalFilter==="all"||(externalFilter==="completed"?isExternalComplete(x):!isExternalComplete(x)));
  return <>
    <div className="card">
      <div className="cardHead"><div><h3>معاملات و سفارش‌ها</h3><p>سفارش‌های CryptoSniper؛ باز، تکمیل‌شده و ناموفق</p></div><div className="row gap"><button type="button" className="primary" onClick={()=>setPage("newtrade")}><PlusCircle size={17}/> معامله جدید</button><select className="smallSelect" value={filter} onChange={e=>setFilter(e.target.value)}><option value="open">باز و فعال</option><option value="all">همه</option><option value="filled">تکمیل‌شده</option><option value="failed">ناموفق</option></select><button type="button" className="softBtn" onClick={load}><RefreshCw size={17}/> تازه‌سازی</button></div></div>
      <TradesTable rows={rows} decimals={decimals} onSelect={x=>setSelected({type:"internal",item:x})}/>
    </div>
    <div className="card sectionGap">
      <div className="cardHead"><div><h3>معاملات خارجی صرافی</h3><p>معاملات ایجادشده خارج از CryptoSniper؛ قابل مشاهده و با Adopt صریح قابل مدیریت</p></div><div className="row gap"><select className="smallSelect" value={externalFilter} onChange={e=>setExternalFilter(e.target.value)}><option value="all">همه</option><option value="open">باز / سفارش جاری</option><option value="completed">تکمیل‌شده / History</option></select><button type="button" className="iconBtn" onClick={load}><RefreshCw size={16}/></button></div></div>
      <div className="tableScroll"><table><thead><tr><th>صرافی</th><th>بازار</th><th>جهت</th><th>قیمت ورود</th><th>مقدار</th><th>وضعیت</th><th>مدیریت</th><th>زمان</th></tr></thead><tbody>{externalRows.map(x=><tr key={x.id} onClick={()=>setSelected({type:"external",item:x})} className="clickRow"><td>{x.exchange}</td><td><b>{x.symbol||"—"}</b></td><td>{x.side==="buy"?"خرید":x.side==="sell"?"فروش":"—"}</td><td>{x.entry_price?fmt(x.entry_price,decimals):"—"}</td><td>{x.quantity?fmt(x.quantity,decimals):"—"}</td><td><span className={isExternalComplete(x)?"status ok":"status warn"}>{isExternalComplete(x)?"تکمیل‌شده":x.status||"باز"}</span></td><td>{x.management?<span className="status ok">{x.management.state||"مدیریت‌شده"}</span>:<span className="pill">خارجی</span>}</td><td>{dt(x.observed_at)}</td></tr>)}</tbody></table>{!externalRows.length&&<Empty text="معامله خارجی در این فیلتر وجود ندارد."/>}</div>
    </div>
    {selected?.type==="internal"&&<TradeDetailDrawer item={selected.item} onClose={()=>setSelected(null)}/>}
    {selected?.type==="external"&&<ExternalTradeDrawer item={selected.item} onClose={()=>setSelected(null)} notify={notify} requestStepUp={requestStepUp} onChanged={load}/>}
  </>
}

function TradesTable({rows,decimals,onSelect}){return <div className="tableScroll"><table><thead><tr><th>بازار</th><th>صرافی</th><th>جهت</th><th>قیمت</th><th>مقدار</th><th>پرشده</th><th>وضعیت</th><th>زمان</th></tr></thead><tbody>{rows.map(x=><tr key={x.id} className={onSelect?"clickRow":""} onClick={()=>onSelect?.(x)}><td><b>{x.symbol||"—"}</b></td><td>{x.exchange}</td><td>{x.side==="buy"?"خرید":"فروش"}</td><td>{x.average_price||x.price?fmt(x.average_price||x.price,decimals):"—"}</td><td>{fmt(x.amount,decimals)}</td><td>{fmt(x.filled_amount,decimals)}</td><td><Status value={x.state}/></td><td>{dt(x.updated_at||x.created_at)}</td></tr>)}</tbody></table>{!rows.length&&<Empty/>}</div>}
function TradeDetailDrawer({item,onClose}){
  const m=item.management;
  return <div className="drawerMask" onClick={onClose}><div className="drawer wideDrawer" onClick={e=>e.stopPropagation()}>
    <div className="cardHead"><div><h3>جزئیات معامله CryptoSniper</h3><p>{item.exchange} · {item.account}</p></div><button type="button" className="iconBtn" onClick={onClose}><X size={18}/></button></div>
    <div className="detailGrid"><Info label="بازار" value={item.symbol}/><Info label="جهت" value={item.side==="buy"?"خرید":"فروش"}/><Info label="نوع سفارش" value={item.order_type}/><Info label="وضعیت سفارش ورود" value={statusFa[item.state]||item.state}/><Info label="قیمت سفارش" value={item.price||"—"}/><Info label="میانگین اجرا" value={item.average_price||"—"}/><Info label="مقدار" value={item.amount}/><Info label="پرشده" value={item.filled_amount}/><Info label="شناسه صرافی" value={item.external_order_id||"—"}/><Info label="خطا" value={item.error_code||"—"}/><Info label="ایجاد" value={dt(item.created_at)}/><Info label="آخرین تغییر" value={dt(item.updated_at)}/></div>
    {m&&<><div className="sectionTitle">مدیریت TP / SL</div><div className="managementStatus"><b>{statusFa[m.state]||m.state}</b><span>باقیمانده: {m.remaining_quantity} · Stop مؤثر: {m.effective_stop} · آخرین قیمت: {m.last_price||"—"}</span><small>Trailing: {m.trailing_enabled?"روشن":"خاموش"} · Trigger: {String(m.trailing_trigger||"tp1").toUpperCase()} · فاصله: {m.trailing_distance_percent}% · Trailing SL: {m.trailing_sl_enabled?"روشن":"خاموش"}</small>{m.last_error&&<small className="down">{m.last_error}</small>}</div><div className="tableScroll"><table><thead><tr><th>هدف</th><th>قیمت</th><th>سهم</th><th>حجم</th><th>وضعیت</th></tr></thead><tbody>{(m.targets||[]).map(t=><tr key={t.position}><td>TP{t.position}</td><td>{t.price}</td><td>{t.share_percent}%</td><td>{t.allocated_quantity}</td><td>{t.state}</td></tr>)}</tbody></table></div></>}
  </div></div>
}

function ExternalTradeDrawer({item,onClose,notify,requestStepUp,onChanged}){
  const [detail,setDetail]=useState({external:item,management:item.management||null});
  const [form,setForm]=useState(null);
  const [busy,setBusy]=useState(false);
  const ext=detail.external||item;
  const management=detail.management;
  const makeForm=(d,m)=>({entry_price:m?.entry_price||d?.entry_price||"",quantity:m?.quantity||d?.quantity||"",stop_loss:m?.stop_loss||"",tp1:m?.tp1||"",tp2:m?.tp2||"",tp3:m?.tp3||"",trailing_enabled:m?.trailing_enabled??true,trailing_sl_enabled:m?.trailing_sl_enabled??true,trailing_trigger:m?.trailing_trigger||"tp1",trailing_distance_percent:String(Math.round(num(m?.trailing_distance_percent||1)))});
  const load=async()=>{try{const d=await api("/api/v1/external-trades/"+item.id+"/management/");setDetail(d);setForm(makeForm(d.external,d.management))}catch(e){setForm(makeForm(item,item.management));}};
  useEffect(()=>{load()},[item.id]);
  const save=async()=>{
    const run=async()=>{try{setBusy(true);const d=await api("/api/v1/external-trades/"+item.id+"/management/",{method:"POST",body:{action:"save",confirmed:true,...form}});setDetail(d);setForm(makeForm(d.external,d.management));notify("مدیریت معامله خارجی ذخیره شد");onChanged?.()}catch(e){if(e.status===403&&e.data?.error==="step_up_required")requestStepUp(run);else notify(e.message)}finally{setBusy(false)}};
    await run();
  };
  const stateAction=async action=>{const run=async()=>{try{setBusy(true);const d=await api("/api/v1/external-trades/"+item.id+"/management/",{method:"POST",body:{action}});setDetail(d);notify(action==="pause"?"مدیریت متوقف شد":"مدیریت ادامه یافت");onChanged?.()}catch(e){if(e.status===403&&e.data?.error==="step_up_required")requestStepUp(run);else notify(e.message)}finally{setBusy(false)}};await run()};
  const canManage=ext.side==="buy"&&management?.state!=="closed";
  return <div className="drawerMask" onClick={onClose}><div className="drawer wideDrawer" onClick={e=>e.stopPropagation()}><div className="cardHead"><div><h3>جزئیات معامله خارجی</h3><p>{ext.exchange} · {ext.account}</p></div><button type="button" className="iconBtn" onClick={onClose}><X size={18}/></button></div>
    <div className="detailGrid"><Info label="بازار" value={ext.symbol||"—"}/><Info label="جهت" value={ext.side==="buy"?"خرید":ext.side==="sell"?"فروش":"—"}/><Info label="قیمت ورود" value={ext.entry_price||"—"}/><Info label="مقدار" value={ext.quantity||"—"}/><Info label="وضعیت" value={isExternalComplete(ext)?"تکمیل‌شده":ext.status||"باز"}/><Info label="شناسه خارجی" value={ext.external_id}/><Info label="زمان مشاهده" value={dt(ext.observed_at)}/><Info label="مدیریت" value={management?.state||"مدیریت نشده"}/></div>
    {management&&<div className="managementStatus"><b>وضعیت مدیریت</b><span>Stop مؤثر: {management.effective_stop||"—"} · آخرین قیمت: {management.last_price||"—"} · آخرین Tick: {dt(management.last_tick_at)}</span>{management.last_error&&<small className="down">{management.last_error}</small>}</div>}
    {canManage&&form&&<><div className="sectionTitle">مدیریت معامله خارجی</div><div className="formGrid"><div className="field"><label>Entry</label><input value={form.entry_price} onChange={e=>setForm({...form,entry_price:e.target.value})}/></div><div className="field"><label>مقدار تحت مدیریت</label><input value={form.quantity} onChange={e=>setForm({...form,quantity:e.target.value})}/></div><div className="field"><label>Stop Loss</label><input value={form.stop_loss} onChange={e=>setForm({...form,stop_loss:e.target.value})}/></div><div className="field"><label>TP1</label><input value={form.tp1} onChange={e=>setForm({...form,tp1:e.target.value})}/></div><div className="field"><label>TP2</label><input value={form.tp2} onChange={e=>setForm({...form,tp2:e.target.value})}/></div><div className="field"><label>TP3</label><input value={form.tp3} onChange={e=>setForm({...form,tp3:e.target.value})}/></div><label className="toggleCard"><input type="checkbox" checked={form.trailing_enabled} onChange={e=>setForm({...form,trailing_enabled:e.target.checked})}/><div><b>Trailing</b><span>تریلینگ درصدی</span></div></label><label className="toggleCard"><input type="checkbox" checked={form.trailing_sl_enabled} onChange={e=>setForm({...form,trailing_sl_enabled:e.target.checked})}/><div><b>Trailing SL</b><span>TP1 → Entry یک‌بار</span></div></label><div className="field"><label>شروع Trailing</label><select value={form.trailing_trigger} onChange={e=>setForm({...form,trailing_trigger:e.target.value})}><option value="tp1">TP1</option><option value="tp2">TP2</option><option value="tp3">TP3</option></select></div><div className="field"><label>فاصله Trailing ٪</label><input type="number" min="1" max="99" step="1" value={form.trailing_distance_percent} onChange={e=>setForm({...form,trailing_distance_percent:e.target.value.replace(/[^0-9]/g,"")})}/></div></div><div className="submitRow">{management&&<button type="button" className="secondary" disabled={busy} onClick={()=>stateAction(management.state==="paused"?"resume":"pause")}>{management.state==="paused"?"ادامه مدیریت":"توقف مدیریت"}</button>}<button type="button" className="primary" disabled={busy} onClick={save}>{management?"ذخیره تغییرات مدیریت":"اعمال مدیریت روی معامله"}</button></div></>}
    {!canManage&&<div className="warningFoot">فروش خارجی یا مدیریت بسته‌شده فقط در تاریخچه نمایش داده می‌شود. برای خرید تکمیل‌شده فقط وقتی Adopt کنید که Position آن هنوز در صرافی باز و موجودی Base متعلق به همان معامله باشد.</div>}
  </div></div>
}

function MarketPicker({markets,value,onChange,search,setSearch,exchangeName,loading}){
  const [open,setOpen]=useState(false);
  const selected=markets.find(x=>String(x.id)===String(value));
  const q=search.trim().toLowerCase();
  const rows=markets.filter(m=>!q||m.symbol.toLowerCase().includes(q)||m.base.toLowerCase().includes(q));
  const choose=m=>{
    onChange(String(m.id));
    setSearch("");
    setOpen(false);
  };
  return <div className="field marketPickerV2">
    <label>بازار</label>
    <button type="button" disabled={loading||!markets.length} className={"marketSelectButton "+(selected?"selected":"")} onClick={()=>setOpen(v=>!v)}>
      <span>{loading?"در حال دریافت بازارها…":!markets.length?"بازاری موجود نیست":selected?((selected.favorite?"★ ":"")+selected.base+" / USDT"):"انتخاب بازار"}</span>
      <ChevronLeft size={16}/>
    </button>
    {open&&<div className="marketDropdown">
      <div className="searchBox compact"><Search size={16}/><input autoFocus value={search} onChange={e=>setSearch(e.target.value)} placeholder="جست‌وجوی BTC، ETH…" onClick={e=>e.stopPropagation()}/></div>
      <div className="marketOptions">{rows.map(m=><button type="button" key={m.id} className={String(m.id)===String(value)?"active":""} onClick={()=>choose(m)}>
        <span><b>{m.favorite?"★ ":""}{m.base} / USDT</b><small>{m.market_type==="margin"?"Margin x"+Number(m.max_leverage).toFixed(0):"Spot"}{m.favorite?" · منتخب":""}</small></span>
        {String(m.id)===String(value)&&<CheckCircle2 size={16}/>}
      </button>)}{!rows.length&&<Empty text="بازاری با این جست‌وجو پیدا نشد."/>}</div>
    </div>}
    <small>{exchangeName?"ارزهای منتخب "+exchangeName+" در ابتدای فهرست هستند.":"ابتدا حساب صرافی را انتخاب کنید."}</small>
  </div>
}

function NewTrade({boot,decimals,notify,requestStepUp,seed,setManualSeed}){
  const [tab,setTab]=useState(seed?.new_trade_tab||"manual");
  useEffect(()=>{if(seed)setTab("manual")},[seed]);
  const localSetPage=p=>{if(p==="manual"||p==="newtrade")setTab("manual")};
  return <div className="newTradeWorkspace"><div className="card newTradeTabs"><div className="tabs"><button type="button" className={tab==="manual"?"active":""} onClick={()=>setTab("manual")}>معامله دستی</button><button type="button" className={tab==="smart"?"active":""} onClick={()=>setTab("smart")}>تحلیل سیگنال</button></div></div>{tab==="manual"?<Manual boot={boot} decimals={decimals} notify={notify} requestStepUp={requestStepUp} seed={seed}/>:<SmartPaste notify={notify} setPage={localSetPage} setManualSeed={value=>{setManualSeed(value);setTab("manual")}}/>}</div>
}

function Manual({boot,decimals,notify,requestStepUp,seed}){
  const accounts=(boot?.accounts||[]).filter(a=>a.status!=="disabled");
  const [prefs,setPrefs]=useState(null);
  const [accountId,setAccountId]=useState(seed?.account_id||accounts[0]?.id||"");
  const [markets,setMarkets]=useState([]);
  const [marketsLoading,setMarketsLoading]=useState(false);
  const [marketId,setMarketId]=useState(seed?.market_id||"");
  const [marketSearch,setMarketSearch]=useState("");
  const [side,setSide]=useState(seed?.side||"long");
  const [entry,setEntry]=useState(seed?.entry||seed?.entry_price||"");
  const [capital,setCapital]=useState(seed?.capital||"");
  const [tp1,setTp1]=useState(seed?.tp1||seed?.targets?.[0]?.price||"");
  const [tp2,setTp2]=useState(seed?.tp2||seed?.targets?.[1]?.price||"");
  const [tp3,setTp3]=useState(seed?.tp3||seed?.targets?.[2]?.price||"");
  const [sl,setSl]=useState(seed?.stop_loss||"");
  const [risk,setRisk]=useState("1");
  const [leverage,setLeverage]=useState(String(seed?.leverage||"1"));
  const [trailingTP,setTrailingTP]=useState(seed?.percentage_trailing??true);
  const [trailingSL,setTrailingSL]=useState(seed?.trailing_sl??true);
  const [trailingTrigger,setTrailingTrigger]=useState(seed?.percentage_trigger||"tp1");
  const [trailingDistance,setTrailingDistance]=useState(seed?.trailing_distance||"1");
  const [quote,setQuote]=useState(null);
  const [fixloss,setFixloss]=useState(null);
  const [fixBusy,setFixBusy]=useState(false);
  const [confirmed,setConfirmed]=useState(false);
  const [busy,setBusy]=useState(false);

  const market=markets.find(x=>String(x.id)===String(marketId));
  const account=accounts.find(x=>String(x.id)===String(accountId));

  useEffect(()=>{
    api("/api/v1/me/trading-preferences/").then(d=>{
      const p=d.trading_preferences;
      setPrefs(p);
      if(!seed){
        setTrailingTP(p.trailing_tp_enabled!==false);
        setTrailingSL(p.trailing_sl_enabled!==false);
        setTrailingTrigger(p.trailing_trigger||"tp1");
        setTrailingDistance(String(p.trailing_distance_percent||"1"));
      }
    }).catch(()=>{});
  },[]);

  const loadMarkets=async id=>{
    if(!id){setMarkets([]);setMarketsLoading(false);return}
    setMarketsLoading(true);
    setMarkets([]);
    setMarketId("");
    try{
      const d=await api("/api/v1/exchange-accounts/"+id+"/markets/");
      const rows=d.markets||[];
      setMarkets(rows);
      const preferred=seed?.market_id&&rows.find(x=>String(x.id)===String(seed.market_id));
      setMarketId(preferred?.id||"");
    }catch(e){notify("دریافت بازارها انجام نشد: "+e.message)}
    finally{setMarketsLoading(false)}
  };
  useEffect(()=>{loadMarkets(accountId)},[accountId]);

  useEffect(()=>{
    if(!marketId)return;
    let stopped=false;
    const run=async()=>{
      try{
        const d=await api("/api/v1/markets/quotes/?live=1&market="+marketId);
        if(!stopped){
          const q=d.markets?.[0]?.quote;
          setQuote(q);
        }
      }catch{}
    };
    run();
    const timer=setInterval(run,2000);
    return()=>{stopped=true;clearInterval(timer)}
  },[marketId]);

  useEffect(()=>{
    if(market?.market_type==="spot"){
      setLeverage("1");
      if(side==="short")setSide("long");
    }else if(market?.max_leverage&&num(leverage)>num(market.max_leverage)){
      setLeverage(String(market.max_leverage));
    }
  },[marketId,market?.market_type]);

  useEffect(()=>{
    if(!accountId||!marketId||num(entry)<=0||num(sl)<=0||num(entry)===num(sl)||num(risk)<=0){
      setFixloss(null);
      return;
    }
    let cancelled=false;
    setFixBusy(true);
    const timer=setTimeout(async()=>{
      try{
        const d=await api("/api/v1/risk/fix-loss/",{method:"POST",body:{
          account_id:accountId,
          market_id:marketId,
          entry,
          stop:sl,
          risk_percent:risk,
          leverage:market?.market_type==="spot"?"1":leverage
        }});
        if(!cancelled){
          setFixloss(d);
          setCapital(String(Math.max(0,Math.floor(num(d.suggested_notional)))));
        }
      }catch{
        if(!cancelled)setFixloss(null);
      }finally{
        if(!cancelled)setFixBusy(false);
      }
    },250);
    return()=>{cancelled=true;clearTimeout(timer)}
  },[accountId,marketId,entry,sl,risk,leverage,market?.market_type]);

  const pct=value=>{
    if(!num(entry)||!num(value))return null;
    const raw=(num(value)-num(entry))/num(entry)*100;
    return side==="short"?-raw:raw;
  };
  const target=(label,value,setValue)=>{
    const p=pct(value);
    return <div className="field"><label>{label}</label><div className="inputSuffix"><input value={value} onChange={e=>setValue(e.target.value)} inputMode="decimal"/><span>USDT</span></div>{p!==null&&<small className={p>=0?"up":"down"}>{(p>=0?"+":"")+fmt(p,2)+"٪ نسبت به Entry"}</small>}</div>
  };

  const liveOrder=async()=>{
    if(!confirmed){notify("تأیید ریسک سفارش را فعال کنید");return}
    if(!market||!account){notify("حساب و بازار را انتخاب کنید");return}
    if(market.market_type!=="spot"){notify("ارسال مستقیم فعلاً فقط برای Spot فعال است.");return}
    const sameAsSuggested=fixloss&&Math.abs(num(capital)-num(fixloss.suggested_notional))<1e-8;
    let quantity=sameAsSuggested?String(fixloss.suggested_quantity||""):(num(capital)&&num(entry)?String(num(capital)/num(entry)):"");
    if(market.amount_step&&num(quantity)>0){
      const stepText=String(market.amount_step).replace(/0+$/,"").replace(/\.$/,"");
      const places=stepText.includes(".")?stepText.split(".")[1].length:0;
      const factor=10**Math.min(places,12);
      quantity=(Math.floor((num(quantity)+1e-14)*factor)/factor).toFixed(Math.min(places,12));
    }
    if(!quantity||num(quantity)<=0){notify("حجم ورود معتبر نیست");return}
    const retry=()=>liveOrder();
    try{
      setBusy(true);
      const planResponse=await api("/api/v1/manual/plans/",{method:"POST",body:{
        account:accountId,
        market:marketId,
        source:"manual",
        origin_signal:seed?.signal_id||null,
        side,
        entry_price:entry,
        tp1,
        tp2:tp2||null,
        tp3:tp3||null,
        stop_loss:sl,
        capital,
        leverage:market?.market_type==="spot"?"1":leverage,
        trailing_sl:trailingSL,
        percentage_trailing:trailingTP,
        percentage_trigger:trailingTrigger,
        trailing_distance:trailingDistance,
        client_token:crypto.randomUUID()
      }});
      const orderQuantity=String(planResponse.plan?.snapshot?.quantity||quantity||"");
      if(!orderQuantity||num(orderQuantity)<=0)throw new Error("Backend حجم نهایی سفارش را محاسبه نکرد.");
      const d=await api("/api/v1/live-orders/",{method:"POST",body:{
        account:accountId,
        market:marketId,
        side:side==="long"?"buy":"sell",
        amount:orderQuantity,
        price:entry,
        confirmed:true,
        plan_id:planResponse.plan.id,
        plan_revision:planResponse.plan.revision,
        request_key:crypto.randomUUID()
      }});
      notify("سفارش #"+d.order.id+" در صف ارسال به صرافی قرار گرفت");
      location.hash="#/trades";
    }catch(e){
      if(e.status===403&&e.data?.error==="step_up_required")requestStepUp(retry);else notify("ارسال سفارش انجام نشد: "+e.message)
    }finally{setBusy(false)}
  };

  return <div className="manualLayout">
    <div className="card tradeForm">
      <div className="cardHead"><div><h3>تعریف معامله</h3><p>قیمت زنده، حجم ورود، TP/SL و Fix Loss خودکار</p></div><span className="liveBadge"><span/> LIVE</span></div>
      <div className="formGrid">
        <div className="field"><label>حساب صرافی</label><select value={accountId} onChange={e=>{setAccountId(e.target.value);setMarketSearch("")}}>{accounts.map(a=><option key={a.id} value={a.id}>{a.exchange_name+" · "+a.label}</option>)}</select></div>
        <MarketPicker markets={markets} value={marketId} onChange={value=>{setMarketId(value);setQuote(null)}} search={marketSearch} setSearch={setMarketSearch} exchangeName={account?.exchange_name||""} loading={marketsLoading}/>
        <div className="field"><label>قیمت زنده</label><div className="livePrice">{quote?.price?fmt(quote.price,num(quote.price)<10?4:2):"ناموجود"}<span>USDT</span></div><small>{quote?.stale?"قیمت قدیمی است":"به‌روزرسانی مستقیم هر ۲ ثانیه"}</small></div>
        <div className="field"><label>جهت</label><div className="segmented"><button type="button" className={side==="long"?"active":""} onClick={()=>setSide("long")}>لانگ</button><button type="button" disabled={market?.market_type==="spot"} className={side==="short"?"active danger":""} onClick={()=>setSide("short")}>شورت</button></div></div>
        <div className="field"><label>Entry</label><input value={entry} onChange={e=>setEntry(e.target.value)} inputMode="decimal"/></div>
        <div className="field"><label>حجم ورود</label><div className="inputSuffix"><input type="number" step="1" min="1" value={capital} onChange={e=>setCapital(e.target.value.replace(/[^0-9]/g,""))} inputMode="numeric"/><span>USDT</span></div><small>فقط عدد صحیح؛ پیشنهاد Fix Loss به پایین گرد می‌شود تا از ریسک تعیین‌شده عبور نکند.</small></div>
        <div className="field"><label>اهرم</label><select disabled={market?.market_type==="spot"} value={market?.market_type==="spot"?"1":leverage} onChange={e=>setLeverage(e.target.value)}>{Array.from({length:Math.max(1,Math.floor(num(market?.max_leverage||1)))},(_,i)=>i+1).map(x=><option key={x} value={x}>{"x"+x}</option>)}</select><small>{market?.market_type==="spot"?"Spot بدون اهرم است.":"اهرم بر اساس سقف همین بازار"}</small></div>
      </div>
      <div className="sectionTitle">اهداف و حد ضرر</div>
      <div className="targetsGrid">{target("TP1",tp1,setTp1)}{target("TP2",tp2,setTp2)}{target("TP3",tp3,setTp3)}{target("Stop Loss",sl,setSl)}</div>
      <div className="sectionTitle">Trailing</div>
      <div className="trailingGrid">
        <label className="toggleCard"><input type="checkbox" checked={trailingTP} onChange={e=>setTrailingTP(e.target.checked)}/><div><b>Trailing</b><span>تریلینگ درصدی</span></div></label>
        <label className="toggleCard"><input type="checkbox" checked={trailingSL} onChange={e=>setTrailingSL(e.target.checked)}/><div><b>Trailing SL</b><span>پیش‌فرض روشن</span></div></label>
        <div className="field"><label>شروع Trailing</label><select value={trailingTrigger} onChange={e=>setTrailingTrigger(e.target.value)}><option value="tp1">TP1</option><option value="tp2">TP2</option><option value="tp3">TP3</option></select></div>
        <div className="field"><label>فاصله Trailing</label><div className="inputSuffix"><input type="number" step="1" min="1" max="99" value={trailingDistance} onChange={e=>setTrailingDistance(e.target.value.replace(/[^0-9]/g,""))} inputMode="numeric"/><span>٪</span></div></div>
      </div>
      <div className="fixBox">
        <div className="fixHead"><div><ShieldCheck size={20}/><div><b>Fix Loss خودکار</b><span>بر اساس تتر آزاد همان صرافی، Entry، Stop و درصد ریسک</span></div></div>{fixBusy&&<LoaderCircle className="spin" size={18}/>}</div>
        <div className="fixGrid">
          <div className="field"><label>ریسک مجاز</label><div className="inputSuffix"><input value={risk} onChange={e=>setRisk(e.target.value)} inputMode="decimal"/><span>٪</span></div></div>
          <div className="suggestion"><span>تتر آزاد</span><strong>{fixloss?(fmt(fixloss.available,2)+" USDT"):"—"}</strong><small>{fixloss?("بودجه ریسک: "+fmt(fixloss.risk_budget,2)+" USDT"):"Entry و Stop را وارد کنید"}</small></div>
          <div className="suggestion"><span>حجم پیشنهادی</span><strong>{fixloss?(fmt(fixloss.suggested_notional,2)+" USDT"):"—"}</strong><small>{fixloss?("فاصله Stop: "+fmt(fixloss.stop_distance_percent,2)+"٪"):"به‌صورت خودکار محاسبه می‌شود"}</small></div>
        </div>
      </div>
      <label className="confirmLine"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/><span>ریسک ارسال سفارش واقعی را تأیید می‌کنم. API صرافی باید بدون مجوز برداشت باشد.</span></label>
      <div className="submitRow"><button type="button" className="primary large" disabled={busy} onClick={liveOrder}><Send size={17}/> ارسال سفارش</button></div>
      <div className="warningFoot">TP/SL و تنظیمات Trailing همراه برنامه معامله ثبت می‌شوند. اجرای خروج واقعی فقط در Adapterهایی فعال می‌شود که چرخه خروجشان کامل شده باشد.</div>
    </div>
    <div className="card chartPanel"><div className="cardHead"><div><h3>{market?.base||"بازار"} <small>/ USDT</small></h3><p>{account?.exchange_name||""}</p></div><b className="up">{quote?.price||"—"}</b></div><MarketChart marketId={marketId} levels={{entry,stop:sl,targets:[tp1,tp2,tp3].filter(Boolean),current:quote?.price}}/></div>
  </div>
}

function ManualPlans({notify,setPage,setManualSeed}){const [plans,setPlans]=useState([]);const load=()=>api("/api/v1/ui/manual-plans/").then(d=>setPlans(d.plans||[])).catch(e=>notify(e.message));useEffect(()=>{load()},[]);const edit=x=>{setManualSeed({...x,plan_id:x.id});setPage("manual")};const confirmPlan=async x=>{try{await api(`/api/v1/manual/plans/${x.id}/confirm/`,{method:"POST",body:{revision:x.revision}});notify(`برنامه #${x.id} تأیید شد؛ هنوز سفارشی ارسال نشده است.`);load()}catch(e){notify(e.message)}};return <div className="card"><div className="cardHead"><div><h3>برنامه‌های معامله</h3><p>برنامه‌ها تنظیمات معامله‌اند؛ تأیید برنامه به‌تنهایی سفارش واقعی ارسال نمی‌کند.</p></div><div className="row gap"><button className="iconBtn" onClick={load}><RefreshCw size={17}/></button><button className="primary" onClick={()=>{setManualSeed(null);setPage("manual")}}><PlusCircle size={17}/> برنامه جدید</button></div></div><div className="tableScroll"><table><thead><tr><th>بازار</th><th>حساب</th><th>جهت</th><th>Entry</th><th>TP / SL</th><th>حجم</th><th>اهرم</th><th>وضعیت</th><th>عملیات</th></tr></thead><tbody>{plans.map(x=><tr key={x.id}><td><b>{(x.symbol||"").replace("/USDT","")}</b><small className="blockMuted">{x.market_type}</small></td><td>{x.exchange} · {x.account}</td><td>{x.side==="long"?"لانگ":"شورت"}</td><td>{x.entry}</td><td><span className="up">TP1 {x.tp1}</span><small className="blockMuted down">SL {x.stop_loss}</small></td><td>{fmt(x.capital,2)} USDT</td><td>x{Number(x.leverage||1).toFixed(0)}</td><td><span className="pill">{x.status==="ready"?"تأییدشده":"پیش‌نویس"}</span></td><td><div className="row gap">{x.status==="draft"&&<button className="softBtn" onClick={()=>edit(x)}>ویرایش</button>}{x.status==="draft"&&<button className="primary" onClick={()=>confirmPlan(x)}><CheckCircle2 size={15}/> تأیید</button>}</div></td></tr>)}</tbody></table>{!plans.length&&<Empty/>}</div></div>}

function MarketChart({marketId,levels={}}){
  const [rows,setRows]=useState([]);
  useEffect(()=>{if(marketId)api("/api/v1/markets/"+marketId+"/candles/").then(d=>setRows(d.candles||[])).catch(()=>setRows([]))},[marketId]);
  const closes=rows.map(x=>num(x.close)).filter(Boolean);
  const levelValues=[num(levels.entry),num(levels.stop),num(levels.current),...(levels.targets||[]).map(num)].filter(v=>v>0);
  const values=[...closes,...levelValues];
  if(!values.length)return <div className="chartEmpty">قیمت زنده پس از انتخاب بازار نمایش داده می‌شود.</div>;
  const min=Math.min(...values),max=Math.max(...values),span=max-min||1;
  const y=v=>160-(v-min)/span*130;
  const pts=closes.length>1?closes.map((v,i)=>(i/(closes.length-1)*600)+","+y(v)).join(" "):"";
  const lines=[["Entry",levels.entry,"entry"],["SL",levels.stop,"stop"],...((levels.targets||[]).map((v,i)=>["TP"+(i+1),v,"target"])),["Now",levels.current,"current"]].filter(x=>num(x[1])>0);
  return <div className="realChart signalLevels"><svg viewBox="0 0 600 180" preserveAspectRatio="none">{pts&&<polyline points={pts} fill="none" stroke="currentColor" strokeWidth="3"/>}{lines.map(([label,v,kind])=><g key={label}><line x1="0" x2="600" y1={y(num(v))} y2={y(num(v))} className={"levelLine "+kind}/><text x="8" y={Math.max(12,y(num(v))-4)} className={"levelText "+kind}>{label} {v}</text></g>)}</svg></div>
}
function SignalMiniChart({signal,onOpen}){
  const [quote,setQuote]=useState(signal.quote||null);
  const [candles,setCandles]=useState([]);
  useEffect(()=>{if(!signal.market_id)return;api("/api/v1/markets/"+signal.market_id+"/candles/").then(d=>setCandles(d.candles||[])).catch(()=>{});const run=()=>api("/api/v1/markets/quotes/?live=1&market="+signal.market_id).then(d=>setQuote(d.markets?.[0]?.quote||null)).catch(()=>{});run();const t=setInterval(run,2000);return()=>clearInterval(t)},[signal.market_id]);
  const closes=candles.map(x=>num(x.close)).filter(Boolean);
  const levels=[num(signal.entry),num(signal.stop_loss),num(quote?.price),...(signal.targets||[]).map(x=>num(x.price))].filter(v=>v>0);
  const values=[...closes,...levels];
  const min=values.length?Math.min(...values):0,max=values.length?Math.max(...values):1,span=max-min||1;
  const y=v=>118-(v-min)/span*92;
  const pts=closes.length>1?closes.map((v,i)=>(i/(closes.length-1)*360)+","+y(v)).join(" "):"";
  return <button type="button" className="signalMiniCard" onClick={onOpen}><div className="signalMiniHead"><div><b>{signal.symbol||("Signal #"+signal.id)}</b><span>{signal.exchange||signal.source_method} · {signal.side||"—"}</span></div><Status value={signal.status}/></div><svg viewBox="0 0 360 130" preserveAspectRatio="none">{pts&&<polyline points={pts} fill="none" stroke="currentColor" strokeWidth="2.5"/>}{num(signal.entry)>0&&<line x1="0" x2="360" y1={y(num(signal.entry))} y2={y(num(signal.entry))} className="levelLine entry"/>}{num(signal.stop_loss)>0&&<line x1="0" x2="360" y1={y(num(signal.stop_loss))} y2={y(num(signal.stop_loss))} className="levelLine stop"/>}{(signal.targets||[]).map((t,i)=><line key={i} x1="0" x2="360" y1={y(num(t.price))} y2={y(num(t.price))} className="levelLine target"/>)}{num(quote?.price)>0&&<line x1="0" x2="360" y1={y(num(quote.price))} y2={y(num(quote.price))} className="levelLine current"/>}</svg><div className="signalLegend"><span>Entry {signal.entry||"—"}</span><span>LIVE {quote?.price||"—"}</span><span>SL {signal.stop_loss||"—"}</span></div></button>
}

function SmartPaste({notify,setPage,setManualSeed}){
  const [text,setText]=useState(()=>localStorage.getItem("cs_smart_text")||"");
  const [result,setResult]=useState(null);
  const [busy,setBusy]=useState(false);
  useEffect(()=>{localStorage.setItem("cs_smart_text",text)},[text]);
  const run=async()=>{try{setBusy(true);const d=await api("/api/v1/smart-paste/",{method:"POST",body:{text}});setResult(d.signal);notify(d.signal?.status==="parsed"?"سیگنال کامل استخراج شد":"سیگنال تحلیل شد؛ موارد ناقص را بازبینی کنید")}catch(e){notify(e.message)}finally{setBusy(false)}};
  const snap=result?.structured||{};
  const parsed=snap.parsed_payload||{};
  const inferredTargets=snap.targets?.length?snap.targets:(parsed.execution_targets||[]).map((price,i)=>({position:i+1,price}));
  const ready=result?.status==="parsed"&&snap.account_id&&snap.market_id&&snap.entry&&snap.stop_loss&&inferredTargets.length;
  const manualSeed=()=>({
    ...snap,
    side:snap.side||parsed.side||"long",
    entry:snap.entry||parsed.entry||"",
    stop_loss:snap.stop_loss||parsed.stop_loss||"",
    targets:inferredTargets,
    leverage:parsed.leverage||"1",
    signal_id:result.id,
    percentage_trailing:parsed.trailing_defaults?.percentage_trailing??true,
    trailing_sl:parsed.trailing_defaults?.trailing_sl??true,
    percentage_trigger:parsed.trailing_defaults?.percentage_trigger||"tp1",
    trailing_distance:parsed.trailing_defaults?.percentage_distance||"1",
    new_trade_tab:"manual"
  });
  return <div className="grid2 equal">
    <div className="card"><div className="cardHead"><div><h3>تحلیل سیگنال</h3><p>استخراج Pair، جهت، Entry، SL، TP و Leverage با قواعد ساختاری</p></div><ClipboardPaste size={20}/></div><textarea className="signalText" value={text} onChange={e=>setText(e.target.value)} placeholder={"BTCUSDT\nLONG\nENTRY 80000\nTP1 82000\nTP2 84000\nSL 78000"}/><div className="submitRow"><button type="button" className="secondary" onClick={()=>{setText("");localStorage.removeItem("cs_smart_text");setResult(null)}}>پاک کردن</button><button type="button" className="primary" disabled={busy||!text.trim()} onClick={run}><Sparkles size={18}/> تحلیل</button></div></div>
    <div className="card"><div className="cardHead"><div><h3>نتیجه تحلیل</h3><p>{result?("Parser "+(snap.parser_version||parsed.parser_version||"—")):"قبل از معامله قابل بازبینی است"}</p></div>{result&&<Status value={result.status}/>}</div>
      {!result?<Empty text="هنوز سیگنالی تحلیل نشده است."/>:<>
        <div className="analysisGrid"><Info label="جفت‌ارز" value={snap.market_id?(parsed.pair||"بازار متصل"):parsed.pair||"—"}/><Info label="جهت" value={snap.side||parsed.side||"—"}/><Info label="Entry" value={snap.entry||parsed.entry||parsed.entry_range?.join(" - ")||"—"}/><Info label="Stop" value={snap.stop_loss||parsed.stop_loss||"—"}/><Info label="Leverage" value={parsed.leverage?("x"+parsed.leverage):"—"}/><Info label="اعتماد ساختاری" value={(snap.technical_confidence??parsed.technical_confidence??0)+"٪"}/>{inferredTargets.map((t,i)=><Info key={i} label={"TP"+(i+1)} value={t.price}/>)}</div>
        {(parsed.warnings||[]).length>0&&<div className="analysisWarnings">{parsed.warnings.map((w,i)=><div key={i}><AlertTriangle size={15}/><span>{w}</span></div>)}</div>}
        <div className="aiNote"><Sparkles size={18}/><div><b>{ready?"بازار و حساب یکتا پیدا شد":"نیازمند بازبینی"}</b><p>{ready?"ساختار کامل است؛ می‌توانید آن را به معامله دستی منتقل و قبل از ارسال دوباره بررسی کنید.":"اگر حساب/بازار یا یکی از قیمت‌ها مشخص نشده، از صندوق سیگنال تکمیل و تأیید کنید."}</p></div></div>
        <div className="submitRow">{ready?<button type="button" className="primary" onClick={()=>{setManualSeed(manualSeed());setPage("manual")}}>انتقال به معامله دستی</button>:<button type="button" className="primary" onClick={()=>setPage("inbox")}>بازبینی در صندوق سیگنال</button>}</div>
      </>}
    </div>
  </div>
}
function Info({label,value}){return <div className="infoBox"><span>{label}</span><b>{String(value??"—")}</b></div>}

function SignalInbox({notify,boot,setPage,setManualSeed}){
  const [items,setItems]=useState([]);
  const [selected,setSelected]=useState(null);
  const [detail,setDetail]=useState(null);
  const [reason,setReason]=useState("");
  const [edit,setEdit]=useState(null);
  const [markets,setMarkets]=useState([]);
  const [checked,setChecked]=useState([]);
  const [busy,setBusy]=useState(false);
  const load=()=>api("/api/v1/inbox/").then(d=>{const next=d.items||[];setItems(next);setChecked(prev=>prev.filter(id=>next.some(x=>x.id===id)))}).catch(e=>notify(e.message));
  useEffect(()=>{load();const t=setInterval(load,10000);return()=>clearInterval(t)},[]);
  const editFrom=z=>({
    account_id:z.account_id||"",
    market_id:z.market_id||"",
    side:z.side||z.parsed_payload?.side||"long",
    entry_price:z.entry||z.parsed_payload?.entry||"",
    stop_loss:z.stop_loss||z.parsed_payload?.stop_loss||"",
    tp1:z.targets?.[0]?.price||z.parsed_payload?.execution_targets?.[0]||"",
    tp2:z.targets?.[1]?.price||z.parsed_payload?.execution_targets?.[1]||"",
    tp3:z.targets?.[2]?.price||z.parsed_payload?.execution_targets?.[2]||""
  });
  const open=async id=>{
    setSelected(id);
    try{
      const d=await api("/api/v1/inbox/"+id+"/");
      const z=d.signal.structured||{};
      setDetail(d.signal);setEdit(editFrom(z));setReason("");
      if(z.account_id){const m=await api("/api/v1/exchange-accounts/"+z.account_id+"/markets/");setMarkets(m.markets||[])}else setMarkets([]);
    }catch(e){notify(e.message)}
  };
  const changeAccount=async value=>{
    setEdit(v=>({...v,account_id:value,market_id:""}));
    try{const m=await api("/api/v1/exchange-accounts/"+value+"/markets/");setMarkets(m.markets||[])}catch(e){notify(e.message)}
  };
  const removeCurrent=()=>{setSelected(null);setDetail(null);setEdit(null);setReason("");load()};
  const deleteOne=async()=>{
    if(!detail||!confirm("این سیگنال کامل حذف شود؟"))return;
    try{await api("/api/v1/inbox/"+detail.id+"/action/",{method:"POST",body:{action:"delete"}});notify("سیگنال حذف شد");removeCurrent()}catch(e){notify(e.message)}
  };
  const saveEdit=async()=>{
    if(!detail||!edit)throw new Error("سیگنال انتخاب نشده است");
    const d=await api("/api/v1/inbox/"+detail.id+"/edit/",{method:"POST",body:{...edit,revision:detail.revision,reason}});
    setDetail(d.signal);setEdit(editFrom(d.signal.structured||{}));setReason("");load();
    return d.signal;
  };
  const approveAndTransfer=async()=>{
    if(!detail||!edit)return;
    try{
      setBusy(true);
      const saved=await saveEdit();
      const approved=await api("/api/v1/inbox/"+saved.id+"/action/",{method:"POST",body:{revision:saved.revision,action:"approve",reason:""}});
      const z=approved.signal?.structured||{};
      const parsed=z.parsed_payload||{};
      setManualSeed({...z,signal_id:approved.signal.id,new_trade_tab:"manual",percentage_trailing:parsed.trailing_defaults?.percentage_trailing??true,trailing_sl:parsed.trailing_defaults?.trailing_sl??true,percentage_trigger:parsed.trailing_defaults?.percentage_trigger||"tp1",trailing_distance:parsed.trailing_defaults?.percentage_distance||"1"});
      notify("سیگنال تأیید شد و فرم معامله با مقادیر آن باز شد");
      setPage("newtrade");
    }catch(e){notify("تأیید انجام نشد: "+e.message)}finally{setBusy(false)}
  };
  const toggleCheck=id=>setChecked(v=>v.includes(id)?v.filter(x=>x!==id):[...v,id]);
  const allChecked=items.length>0&&items.every(x=>checked.includes(x.id));
  const bulkDelete=async()=>{
    if(!checked.length||!confirm(checked.length+" سیگنال انتخاب‌شده حذف شود؟"))return;
    try{setBusy(true);const d=await api("/api/v1/inbox/bulk-action/",{method:"POST",body:{action:"delete",ids:checked}});notify(d.count+" سیگنال حذف شد");setChecked([]);if(selected&&checked.includes(selected)){setSelected(null);setDetail(null);setEdit(null)}await load()}catch(e){notify(e.message)}finally{setBusy(false)}
  };
  return <div className="splitLayout">
    <div className="card">
      <div className="cardHead"><div><h3>صندوق سیگنال</h3><p>انتخاب گروهی، بازبینی و انتقال به معامله</p></div><div className="row gap"><button type="button" className="iconBtn" onClick={load}><RefreshCw size={17}/></button>{checked.length>0&&<button type="button" className="softBtn dangerBtn" disabled={busy} onClick={bulkDelete}><Trash2 size={16}/> حذف {checked.length}</button>}</div></div>
      {items.length>0&&<label className="selectAllLine"><input type="checkbox" checked={allChecked} onChange={()=>setChecked(allChecked?[]:items.map(x=>x.id))}/><span>انتخاب همه</span></label>}
      <div className="signalRows selectable">{items.map(x=><div className={"signalSelectRow "+(selected===x.id?"active":"")} key={x.id}><input type="checkbox" checked={checked.includes(x.id)} onChange={()=>toggleCheck(x.id)}/><button type="button" onClick={()=>open(x.id)}><div><b>{x.symbol||("Signal #"+x.id)}</b><span>{x.source_method}{x.entry?(" · Entry "+x.entry):""}</span></div><Status value={x.status}/></button></div>)}{!items.length&&<Empty/>}</div>
    </div>
    <div className="card">{!detail?<Empty text="یک سیگنال را انتخاب کنید."/>:<>
      <div className="cardHead"><div><h3>سیگنال #{detail.id}</h3><p>Revision {detail.revision}</p></div><Status value={detail.status}/></div>
      <pre className="rawSignal">{detail.raw?.original_text}</pre>
      {edit&&<div className="formGrid">
        <div className="field"><label>حساب صرافی</label><select value={edit.account_id} onChange={e=>changeAccount(e.target.value)}><option value="">انتخاب حساب</option>{(boot?.accounts||[]).filter(a=>a.status==="connected").map(a=><option key={a.id} value={a.id}>{a.exchange_name+" · "+a.label}</option>)}</select></div>
        <div className="field"><label>بازار همان حساب</label><select value={edit.market_id} onChange={e=>setEdit({...edit,market_id:e.target.value})}><option value="">انتخاب بازار</option>{markets.map(m=><option key={m.id} value={m.id}>{m.base+(m.market_type==="margin"?" · Margin":" · Spot")}</option>)}</select></div>
        <div className="field"><label>جهت</label><select value={edit.side} onChange={e=>setEdit({...edit,side:e.target.value})}><option value="long">Long</option><option value="short">Short</option></select></div>
        <div className="field"><label>Entry</label><input value={edit.entry_price} onChange={e=>setEdit({...edit,entry_price:e.target.value})}/></div>
        <div className="field"><label>TP1</label><input value={edit.tp1} onChange={e=>setEdit({...edit,tp1:e.target.value})}/></div>
        <div className="field"><label>TP2</label><input value={edit.tp2} onChange={e=>setEdit({...edit,tp2:e.target.value})}/></div>
        <div className="field"><label>TP3</label><input value={edit.tp3} onChange={e=>setEdit({...edit,tp3:e.target.value})}/></div>
        <div className="field"><label>Stop Loss</label><input value={edit.stop_loss} onChange={e=>setEdit({...edit,stop_loss:e.target.value})}/></div>
      </div>}
      <div className="actionBox"><label>دلیل ویرایش <small>(اختیاری)</small></label><textarea value={reason} onChange={e=>setReason(e.target.value)} placeholder="در صورت نیاز توضیح بنویسید…"/><div className="row gap wrap"><button type="button" className="softBtn" disabled={busy} onClick={()=>saveEdit().then(()=>notify("ویرایش سیگنال ذخیره شد")).catch(e=>notify(e.message))}><Save size={16}/> ذخیره ویرایش</button><button type="button" className="iconBtn dangerBtn" title="حذف سیگنال" disabled={busy} onClick={deleteOne}><Trash2 size={16}/></button><button type="button" className="primary" disabled={busy} onClick={approveAndTransfer}><CheckCircle2 size={16}/> تأیید و انتقال به معامله</button></div></div>
    </>}</div>
  </div>
}
function Exchanges({boot,refreshBoot,notify,requestStepUp}){
  const [catalog,setCatalog]=useState([]);
  const [selected,setSelected]=useState(null);
  const [diag,setDiag]=useState(null);
  const [showAdd,setShowAdd]=useState(false);
  const loadCatalog=()=>api("/api/v1/exchanges/").then(d=>setCatalog((d.exchanges||[]).filter(x=>x.code!=="binance"))).catch(e=>notify(e.message));
  useEffect(()=>{loadCatalog();refreshBoot();const t=setInterval(refreshBoot,5000);return()=>clearInterval(t)},[]);
  const inspect=async a=>{setSelected(a);try{setDiag(await api("/api/v1/exchange-accounts/"+a.id+"/diagnostics/"))}catch(e){notify(e.message)}};
  const sync=async a=>{try{await api("/api/v1/exchange-accounts/"+a.id+"/sync/",{method:"POST",body:{}});notify("همگام‌سازی شروع شد");setTimeout(()=>{refreshBoot();inspect(a)},1200);setTimeout(()=>{refreshBoot();inspect(a)},4000)}catch(e){notify(e.message)}};
  const revoke=async a=>{
    if(!confirm("اتصال "+a.exchange_name+" حذف شود؟ سوابق معاملات حفظ می‌شوند ولی credential حذف می‌شود."))return;
    const run=async()=>{
      try{
        await api("/api/v1/exchange-accounts/"+a.id+"/revoke/",{method:"POST",body:{confirmed:true}});
        notify("اتصال حذف شد");
        setSelected(null);setDiag(null);
        await refreshBoot();
      }catch(e){
        if(e.status===403&&e.data?.error==="step_up_required")requestStepUp(run);else notify(e.message);
      }
    };
    await run();
  };
  const rotate=async a=>{
    if(!confirm("کلید رمزنگاری داخلی این اتصال گردش کند؟"))return;
    const run=async()=>{
      try{await api("/api/v1/exchange-accounts/"+a.id+"/rotate/",{method:"POST",body:{confirmed:true}});notify("کلید رمزنگاری گردش یافت");setTimeout(refreshBoot,1200);setSelected(null);setDiag(null)}
      catch(e){if(e.status===403&&e.data?.error==="step_up_required")requestStepUp(run);else notify(e.message)}
    };
    await run();
  };
  return <>
    <div className="card">
      <div className="cardHead"><div><h3>حساب‌های صرافی</h3><p>وضعیت هر ۵ ثانیه در رابط تازه می‌شود؛ Sync دستی وضعیت Provider را همان لحظه دوباره بررسی می‌کند.</p></div><button type="button" className="primary" onClick={()=>setShowAdd(true)}><PlusCircle size={18}/> افزودن اتصال</button></div>
      <div className="tableScroll"><table><thead><tr><th>صرافی</th><th>USDT آزاد</th><th>آخرین Sync</th><th>وضعیت API</th><th>مجوز معامله</th><th>عملیات</th></tr></thead><tbody>{(boot?.accounts||[]).map(a=>{const usdt=a.balances?.find(b=>b.asset==="USDT");return <tr key={a.id}><td><div className="exchangeName"><span className="exchangeLogo">{a.exchange_name?.[0]||a.exchange?.[0]}</span><div><b>{a.exchange_name}</b><small>{a.label}</small></div></div></td><td className="usdtHighlight">{fmt(usdt?.free||0,2)} USDT</td><td>{dt(a.last_sync_at)}</td><td><Status value={a.status}/></td><td>{a.trading_enabled?<span className="up">Read + Spot تأیید شده</span>:<span className="muted">محدود / نیازمند بررسی</span>}</td><td><div className="row gap"><button type="button" className="softBtn" onClick={()=>inspect(a)}>جزئیات و لاگ</button><button type="button" className="iconBtn" title="همگام‌سازی فوری" onClick={()=>sync(a)}><RefreshCw size={16}/></button><button type="button" className="iconBtn" title="گردش کلید رمزنگاری" onClick={()=>rotate(a)}><KeyRound size={16}/></button><button type="button" className="iconBtn dangerBtn" title="حذف اتصال" onClick={()=>revoke(a)}><Trash2 size={16}/></button></div></td></tr>})}</tbody></table>{!(boot?.accounts||[]).length&&<Empty text="اتصال فعالی وجود ندارد."/>}</div>
    </div>
    {selected&&diag&&<Diagnostics account={selected} data={diag} onRotate={()=>rotate(selected)} onClose={()=>{setSelected(null);setDiag(null)}}/>}
    {showAdd&&<AddExchange catalog={catalog} onClose={()=>setShowAdd(false)} notify={notify} done={async()=>{setShowAdd(false);await refreshBoot();setTimeout(refreshBoot,2500)}}/>}
  </>
}

function Diagnostics({account,data,onClose,onRotate}){const a=data.account;return <div className="drawerMask" onClick={onClose}><div className="drawer wideDrawer" onClick={e=>e.stopPropagation()}><div className="cardHead"><div><h3>لاگ اتصال {account.exchange_name}</h3><p>آخرین وضعیت قابل مشاهده بدون نمایش Secret</p></div><div className="row gap"><button className="softBtn" onClick={onRotate}><KeyRound size={16}/> گردش رمزنگاری</button><button className="iconBtn" onClick={onClose}><X size={18}/></button></div></div><div className="checkGrid">{Object.entries(data.checks||{}).map(([k,v])=><div className="checkItem" key={k}><span>{v===true?"✓":v===false?"✕":"?"}</span><b>{k}</b><small>{String(v)}</small></div>)}</div>{a.last_error?.code&&<div className="errorBox"><AlertTriangle size={18}/><div><b>{a.last_error.code}</b><span>{a.last_error.message}</span><small>{dt(a.last_error.at)}</small></div></div>}<div className="sectionTitle">موجودی‌ها</div><div className="tableScroll"><table><thead><tr><th>دارایی</th><th>آزاد</th><th>قفل</th><th>کل</th></tr></thead><tbody>{(a.balances||[]).map(b=><tr key={b.asset} className={b.asset==="USDT"?"usdtRow":""}><td><b>{b.asset}</b></td><td>{b.free}</td><td>{b.locked}</td><td>{b.total}</td></tr>)}</tbody></table></div></div></div>}
function AddExchange({catalog,onClose,notify,done}){
  const [form,setForm]=useState({exchange:catalog[0]?.code||"",label:"حساب اصلی",api_key:"",api_secret:"",passphrase:"",no_withdrawal_confirmed:false,ip_restricted_confirmed:false});
  const [busy,setBusy]=useState(false);
  useEffect(()=>{if(!form.exchange&&catalog[0])setForm(v=>({...v,exchange:catalog[0].code}))},[catalog]);
  const submit=async()=>{
    if(!form.exchange){notify("صرافی را انتخاب کنید");return}
    if(!form.api_key.trim()){notify("API Key / Token لازم است");return}
    if(form.exchange!=="nobitex"&&!form.api_secret.trim()){notify("API Secret لازم است");return}
    if(form.exchange==="weex"&&!form.passphrase.trim()){notify("Passphrase برای WEEX لازم است");return}
    if(!form.no_withdrawal_confirmed){notify("ابتدا خاموش بودن Withdrawal را تأیید کنید");return}
    try{
      setBusy(true);
      const d=await api("/api/v1/exchange-connections/",{method:"POST",body:form});
      notify("اتصال #"+d.id+" ثبت شد؛ تست Provider در Worker شروع شد");
      await done(d);
    }catch(e){notify(e.message)}
    finally{setBusy(false)}
  };
  return <Modal title="افزودن اتصال صرافی" onClose={onClose}><div className="formGrid oneCol">
    <div className="field"><label>صرافی</label><select value={form.exchange} onChange={e=>setForm({...form,exchange:e.target.value,api_key:"",api_secret:"",passphrase:""})}><option value="">انتخاب صرافی</option>{catalog.map(x=><option value={x.code} key={x.code}>{x.name}</option>)}</select></div>
    <div className="field"><label>نام اتصال</label><input value={form.label} onChange={e=>setForm({...form,label:e.target.value})}/></div>
    <div className="field"><label>{form.exchange==="nobitex"?"Token":"API Key"}</label><input dir="ltr" autoComplete="off" value={form.api_key} onChange={e=>setForm({...form,api_key:e.target.value.trim()})}/></div>
    {form.exchange!=="nobitex"&&<div className="field"><label>API Secret</label><input dir="ltr" type="password" autoComplete="new-password" value={form.api_secret} onChange={e=>setForm({...form,api_secret:e.target.value.trim()})}/></div>}
    {form.exchange==="weex"&&<div className="field"><label>Passphrase</label><input dir="ltr" type="password" value={form.passphrase} onChange={e=>setForm({...form,passphrase:e.target.value})}/></div>}
    <label className="confirmLine"><input type="checkbox" checked={form.no_withdrawal_confirmed} onChange={e=>setForm({...form,no_withdrawal_confirmed:e.target.checked})}/><span>تأیید می‌کنم Withdrawal روی این API خاموش است.</span></label>
    <label className="confirmLine"><input type="checkbox" checked={form.ip_restricted_confirmed} onChange={e=>setForm({...form,ip_restricted_confirmed:e.target.checked})}/><span>IP ثابت سرور در whitelist صرافی ثبت شده است.</span></label>
    <Guide provider={form.exchange}/>
    <button type="button" className="primary fullBtn" disabled={busy||!catalog.length} onClick={submit}>{busy?<LoaderCircle className="spin" size={17}/>:<PlugZap size={17}/>} ثبت و تست اتصال</button>
  </div></Modal>
}

const guides={
  bitunix:[
    "در API Management کلید Read + Spot Trading بسازید.",
    "Withdrawal باید کاملاً خاموش باشد.",
    "در صورت امکان IP ثابت سرور را whitelist کنید."
  ],
  lbank:[
    "Verification Method را HmacSHA256 انتخاب کنید.",
    "Read و Spot Trade روشن و Withdrawal خاموش باشد.",
    "اگر 10005 می‌بینید Key/Secret فعلی در LBank معتبر نیست و باید کلید تازه بسازید."
  ],
  ourbit:[
    "SPOT_ACCOUNT_READ و SPOT_DEAL_WRITE را فعال کنید.",
    "مجوز Withdrawal را فعال نکنید.",
    "خطای 700007 یعنی Permission endpoint حساب ناقص است."
  ],
  weex:[
    "API Key، Secret و Passphrase هر سه لازم‌اند.",
    "Read و Spot Trade روشن و Withdrawal خاموش باشد.",
    "IP ثابت سرور را در whitelist قرار دهید."
  ],
  nobitex:[
    "Token جدید حساب را وارد کنید؛ Secret جداگانه لازم نیست.",
    "Token را بدون پیشوند Token وارد کنید.",
    "اتصال حذف‌شده باید با Token تازه دوباره ثبت شود."
  ]
};

function Guide({provider}){return <div className="guideMini"><b>راهنمای اتصال</b>{(guides[provider]||[]).map((x,i)=><div key={i}><span>{i+1}</span><p>{x}</p></div>)}</div>}

function Wallets({notify}){const [wallets,setWallets]=useState([]);const [provider,setProvider]=useState("metamask");const [network,setNetwork]=useState("ethereum");const [address,setAddress]=useState("");const [label,setLabel]=useState("کیف پول اصلی");const load=()=>api("/api/v1/wallets/").then(d=>setWallets(d.wallets||[])).catch(e=>notify(e.message));useEffect(()=>{load()},[]);const save=async(status="watch_only")=>{try{await api("/api/v1/wallets/",{method:"POST",body:{provider,network,address,label,status}});notify("کیف پول ثبت شد");setAddress("");load()}catch(e){notify(e.message)}};const browserConnect=async()=>{try{if(!window.ethereum)throw new Error("کیف پول مرورگر شناسایی نشد. MetaMask/Trust را در مرورگر فعال کنید.");const accounts=await window.ethereum.request({method:"eth_requestAccounts"});if(!accounts?.[0])throw new Error("آدرسی دریافت نشد");setAddress(accounts[0]);await api("/api/v1/wallets/",{method:"POST",body:{provider,network:"ethereum",address:accounts[0],label,status:"connected"}});notify("کیف پول مرورگر متصل و آدرس عمومی ثبت شد");load()}catch(e){notify(e.message)}};const del=async id=>{try{await api(`/api/v1/wallets/${id}/`,{method:"DELETE"});load()}catch(e){notify(e.message)}};return <div className="walletLayout"><div className="card"><div className="cardHead"><div><h3>کیف پول‌های غیرامانی</h3><p>بدون Seed Phrase و Private Key</p></div><ShieldCheck size={20}/></div><div className="formGrid oneCol"><div className="field"><label>نوع کیف پول</label><select value={provider} onChange={e=>setProvider(e.target.value)}><option value="metamask">MetaMask</option><option value="trust_wallet">Trust Wallet</option><option value="walletconnect">WalletConnect</option><option value="ledger">Ledger</option><option value="trezor">Trezor</option><option value="evm_address">EVM Address</option><option value="tron_address">TRON Address</option></select></div><div className="field"><label>شبکه</label><input value={network} onChange={e=>setNetwork(e.target.value)}/></div><div className="field"><label>نام</label><input value={label} onChange={e=>setLabel(e.target.value)}/></div><div className="field"><label>آدرس عمومی</label><input dir="ltr" value={address} onChange={e=>setAddress(e.target.value)} placeholder="0x… / TRON…"/></div><div className="securityNote"><ShieldCheck size={18}/><div><b>هیچ Secret کیف پول ذخیره نمی‌شود</b><span>اتصال این بخش فقط برای مشاهده/شناسایی آدرس است. تراکنش on-chain نیازمند تأیید جداگانه داخل کیف پول خواهد بود.</span></div></div><div className="row gap"><button className="secondary" onClick={()=>save("watch_only")}>ثبت فقط مشاهده</button>{["metamask","trust_wallet"].includes(provider)&&<button className="primary" onClick={browserConnect}><Link2 size={17}/> اتصال مرورگر</button>}</div></div></div><div className="card"><div className="cardHead"><div><h3>اتصال‌های ثبت‌شده</h3><p>برای مدیریت دارایی‌های چندمحلی</p></div></div><div className="walletList">{wallets.map(w=><div className="walletRow" key={w.id}><div><span className="walletIcon"><WalletCards size={18}/></span><div><b>{w.label}</b><small>{w.provider_label} · {w.network}</small><code>{w.address}</code></div></div><div><Status value={w.status==="connected"?"connected":"restricted"}/><button className="iconBtn dangerBtn" onClick={()=>del(w.id)}><Trash2 size={16}/></button></div></div>)}{!wallets.length&&<Empty/>}</div><div className="guideFooter"><AlertTriangle size={18}/><p>WalletConnect واقعی در مرورگر به Project ID ارائه‌دهنده نیاز دارد. تا زمان تنظیم آن، WalletConnect به‌صورت ثبت آدرس عمومی/فقط مشاهده استفاده می‌شود. Seed Phrase یا Private Key هرگز وارد CryptoSniper نشود.</p></div></div></div>}

function Watchlist({boot,notify,setPage,setManualSeed}){const [data,setData]=useState({watchlists:[]});const [active,setActive]=useState(null);const [q,setQ]=useState("");const [results,setResults]=useState([]);const [favorites,setFavorites]=useState(boot?.favorites||[]);const load=()=>api("/api/v1/ui/watchlists/").then(d=>{setData(d);if(!active&&d.watchlists?.[0])setActive(d.watchlists[0].id)});useEffect(()=>{load()},[]);useEffect(()=>{const t=setTimeout(()=>{if(q.trim())api(`/api/v1/markets/search/?q=${encodeURIComponent(q)}`).then(d=>setResults(d.results||[]));else setResults([])},300);return()=>clearTimeout(t)},[q]);const wl=data.watchlists.find(x=>x.id===active);const add=async m=>{try{await api("/api/v1/ui/watchlists/",{method:"POST",body:{action:"add",watchlist_id:active,market_id:m.id}});notify("بازار اضافه شد");load()}catch(e){notify(e.message)}};const remove=async item=>{await api("/api/v1/ui/watchlists/",{method:"POST",body:{action:"remove",watchlist_id:active,item_id:item.id}});load()};const saveFav=async arr=>{setFavorites(arr);try{await api("/api/v1/ui/favorites/",{method:"POST",body:{symbols:arr}})}catch(e){notify(e.message)}};const toggleFav=s=>saveFav(favorites.includes(s)?favorites.filter(x=>x!==s):[...favorites,s]);return <div className="grid2 equal"><div className="card"><div className="cardHead"><div><h3>ارزهای اولویت‌دار</h3><p>در همه فهرست‌های بازار بالاتر نمایش داده می‌شوند</p></div></div><div className="favoriteList">{favorites.map((f,i)=><div className="favoriteRow" key={f}><GripVertical size={18}/><span className="coinIcon">{f[0]}</span><b>{f}</b><span className="muted">اولویت {i+1}</span><button className="iconBtn" onClick={()=>saveFav(favorites.filter(x=>x!==f))}><X size={16}/></button></div>)}</div><div className="searchBox"><Search size={18}/><input placeholder="جست‌وجوی ارز…" value={q} onChange={e=>setQ(e.target.value)}/></div><div className="marketList">{results.sort((a,b)=>(favorites.includes(b.base_asset)?1:0)-(favorites.includes(a.base_asset)?1:0)).map(m=><div className="marketRow" key={m.id}><div><span className="coinIcon">{m.base_asset[0]}</span><b>{m.base_asset}</b>{m.market_type==="margin"&&<span className="pill">Margin</span>}</div><span>{m.exchange_name}</span><div><button className="iconBtn" onClick={()=>toggleFav(m.base_asset)}><Star size={17}/></button><button className="softBtn" onClick={()=>add(m)}>افزودن</button><button className="primary mini" onClick={()=>{setManualSeed({market_id:m.id,account_id:boot?.accounts?.find(a=>a.exchange===m.exchange)?.id});setPage("manual")}}>معامله</button></div></div>)}</div></div><div className="card"><div className="cardHead"><div><h3>دیده‌بان</h3><p>قیمت زنده بازارهای منتخب</p></div><select className="smallSelect" value={active||""} onChange={e=>setActive(Number(e.target.value))}>{data.watchlists.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select></div><div className="marketList">{(wl?.items||[]).map(m=><div className="marketRow" key={m.id}><div><span className="coinIcon">{m.base[0]}</span><b>{m.base}</b>{num(m.max_leverage)>1&&<span className="pill">x{Number(m.max_leverage).toFixed(0)}</span>}</div><span className={m.quote?.stale?"muted":"up"}>{m.quote?.price||"—"}</span><div><button className="softBtn" onClick={()=>{setManualSeed({market_id:m.market_id,account_id:boot?.accounts?.find(a=>a.exchange===m.exchange)?.id});setPage("manual")}}>سیگنال دستی</button><button className="iconBtn dangerBtn" onClick={()=>remove(m)}><Trash2 size={16}/></button></div></div>)}{!wl?.items?.length&&<Empty/>}</div></div></div>}

function Telegram({notify,setPage,setManualSeed,requestStepUp}){const [state,setState]=useState(null);const [messages,setMessages]=useState([]);const [q,setQ]=useState("");const [channel,setChannel]=useState("");const [analytics,setAnalytics]=useState(null);const [connect,setConnect]=useState({api_id:"",api_hash:"",phone:"",code:"",password:""});const load=()=>Promise.all([api("/api/v1/telegram/state/"),api(`/api/v1/telegram/messages/?q=${encodeURIComponent(q)}${channel?`&channel=${channel}`:""}`)]).then(([st,m])=>{setState(st);setMessages(m.messages||[])}).catch(e=>notify(e.message));useEffect(()=>{load()},[]);useEffect(()=>{const t=setTimeout(()=>api(`/api/v1/telegram/messages/?q=${encodeURIComponent(q)}${channel?`&channel=${channel}`:""}`).then(d=>setMessages(d.messages||[])).catch(()=>{}),350);return()=>clearTimeout(t)},[q,channel]);const act=async body=>{try{const d=await api("/api/v1/telegram/action/",{method:"POST",body});if(d.discovered)notify(`${d.discovered.length} کانال پیدا شد`);else notify("عملیات Telegram انجام شد");load()}catch(e){if(e.status===403)requestStepUp();else notify(e.message)}};const loadAnalytics=async()=>{if(!channel)return;try{setAnalytics(await api(`/api/v1/telegram/channels/${channel}/analytics/`))}catch(e){notify(e.message)}};const toSmart=m=>{navigator.clipboard?.writeText(m.text);localStorage.setItem("cs_smart_text",m.text);setPage("smart")};const chosen=(state?.channels||[]).find(x=>String(x.id)===String(channel));return <div className="telegramLayout"><div className="card channels"><div className="cardHead"><div><h3>حساب Telegram</h3><p>{state?.account?.status||"—"}{state?.account?.phone_hint?` · ${state.account.phone_hint}`:""}</p></div><Status value={state?.account?.status==="connected"?"connected":"pending"}/></div>{state?.account?.status!=="connected"?<div className="connectBox"><input placeholder="API ID" value={connect.api_id} onChange={e=>setConnect({...connect,api_id:e.target.value})}/><input placeholder="API Hash" type="password" value={connect.api_hash} onChange={e=>setConnect({...connect,api_hash:e.target.value})}/><input placeholder="+98…" value={connect.phone} onChange={e=>setConnect({...connect,phone:e.target.value})}/><button className="primary" onClick={()=>act({action:"connect",api_id:connect.api_id,api_hash:connect.api_hash,phone:connect.phone})}>درخواست کد</button><input placeholder="کد ورود" value={connect.code} onChange={e=>setConnect({...connect,code:e.target.value})}/><input placeholder="رمز دومرحله‌ای" type="password" value={connect.password} onChange={e=>setConnect({...connect,password:e.target.value})}/><button className="secondary" onClick={()=>act({action:"code",code:connect.code,password:connect.password})}>تأیید کد</button></div>:<><div className="row gap pad12"><button className="softBtn" onClick={()=>act({action:"refresh"})}><RefreshCw size={16}/> دریافت کانال‌ها</button><button className="softBtn dangerLite" onClick={()=>confirm("اتصال Telegram قطع شود؟")&&act({action:"revoke"})}>قطع اتصال</button></div><div className="discovered">{(state?.discovered||[]).map(x=><div key={x.peer_id}><span>{x.title}</span><button className="linkBtn" onClick={()=>act({action:"channel",peer_id:x.peer_id,parse_mode:"hybrid",min_confidence:80,capital:100})}>افزودن</button></div>)}</div></>}<div className="channelList">{(state?.channels||[]).map(c=><button className={String(channel)===String(c.id)?"active":""} key={c.id} onClick={()=>{setChannel(c.id);setAnalytics(null)}}><div><b>{c.title}</b><small>{c.parse_mode} · {c.enabled?"زنده":"متوقف"} · {c.backfill?.status||"بدون آرشیو"}</small></div><span>{c.backfill?.imported||0}</span></button>)}</div></div><div className="card telegramFeed"><div className="cardHead"><div><h3>پیام‌های گذشته و آینده</h3><p>جست‌وجو با متن، هشتگ یا نماد</p></div><div className="row gap">{chosen&&<button className="softBtn" onClick={()=>act({action:"toggle",channel_id:chosen.id})}>{chosen.enabled?"توقف دریافت زنده":"فعال‌سازی زنده"}</button>}{chosen?.backfill&&["running","pending"].includes(chosen.backfill.status)?<button className="softBtn" onClick={()=>act({action:"archive_pause",job_id:chosen.backfill.id})}>توقف آرشیو</button>:channel&&<button className="softBtn" onClick={()=>act({action:"archive_start",channel_id:channel})}>دریافت از اولین پیام</button>}{channel&&<button className="softBtn" onClick={loadAnalytics}><BarChart3 size={16}/> آمار کانال</button>}<button className="iconBtn" onClick={load}><RefreshCw size={17}/></button></div></div>{analytics&&<div className="analyticsBox"><div className="row gap"><b>آمار کانال #{analytics.channel_id}</b><Status value={analytics.evaluation?.status}/></div><div className="analysisGrid">{Object.entries(analytics.metrics||{}).slice(0,12).map(([k,v])=><Info key={k} label={k} value={typeof v==="object"?JSON.stringify(v):String(v??"—")}/>)}</div>{analytics.evaluation&&<p className="muted">ارزیابی: {analytics.evaluation.evaluated}/{analytics.evaluation.total} · ردشده/صرف‌نظر: {analytics.evaluation.skipped}</p>}</div>}<div className="searchBox"><Search size={18}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="#BTC، Entry، متن پیام…"/></div><div className="messageList">{messages.map(m=><div className="messageCard" key={m.id}><div className="messageMeta"><b>{m.channel}</b><span>{dt(m.occurred_at)}</span><span className="pill">{m.kind}</span></div><pre>{m.text}</pre><div className="messageActions"><button className="softBtn" onClick={()=>navigator.clipboard?.writeText(m.text)}><Copy size={16}/> کپی</button><button className="primary" onClick={()=>toSmart(m)}><Sparkles size={16}/> ارسال به تحلیل سیگنال</button></div></div>)}{!messages.length&&<Empty/>}</div></div></div>}
function Alerts({notify}){const blank={id:null,version:1,title:"",kind:"price",threshold:"",market:"",direction:"above",repeat:false,hysteresis:"0.1",cooldown_seconds:60,enabled:true};const [items,setItems]=useState([]);const [notes,setNotes]=useState([]);const [q,setQ]=useState("");const [markets,setMarkets]=useState([]);const [form,setForm]=useState(blank);const load=()=>Promise.all([api("/api/v1/alerts/"),api("/api/v1/notifications/")]).then(([a,n])=>{setItems(a.alerts||[]);setNotes(n.items||[])}).catch(e=>notify(e.message));useEffect(()=>{load()},[]);useEffect(()=>{const t=setTimeout(()=>{if(q.trim())api(`/api/v1/markets/search/?q=${encodeURIComponent(q)}`).then(d=>setMarkets((d.results||[]).filter(x=>x.market_type==="spot")));else setMarkets([])},300);return()=>clearTimeout(t)},[q]);const save=async(next=form)=>{try{await api("/api/v1/alerts/",{method:"POST",body:{...next,market:next.market,trade:""}});notify(next.id?"هشدار ویرایش شد":"هشدار ذخیره شد");setForm(blank);setQ("");load()}catch(e){notify(e.message)}};const edit=a=>{setForm({id:a.id,version:a.version,title:a.title,kind:a.kind,threshold:a.threshold,market:String(a.market_id),direction:a.direction||"above",repeat:!!a.repeat,hysteresis:a.hysteresis||"0.1",cooldown_seconds:a.cooldown_seconds||60,enabled:a.enabled});setQ(a.market_symbol||"");setMarkets([{id:a.market_id,base_asset:(a.market_symbol||"").replace("/USDT",""),exchange_name:a.market_exchange}]);};const toggle=a=>save({id:a.id,version:a.version,title:a.title,kind:a.kind,threshold:a.threshold,market:String(a.market_id),direction:a.direction||"above",repeat:!!a.repeat,hysteresis:a.hysteresis||"0.1",cooldown_seconds:a.cooldown_seconds||60,enabled:!a.enabled});const markRead=async id=>{try{await api(`/api/v1/notifications/${id}/read/`,{method:"POST",body:{}});load()}catch(e){notify(e.message)}};return <><div className="grid2 equal"><div className="card"><div className="cardHead"><div><h3>هشدارها</h3><p>هشدار فقط اطلاع‌رسانی می‌کند و معامله را تغییر نمی‌دهد</p></div></div><div className="simpleList">{items.map(a=><div key={a.id}><div><b>{a.title}</b><span>{a.market_symbol} · {a.kind} · {a.threshold} · {a.fire_count} اعلان</span></div><div className="row gap"><Status value={a.enabled?"connected":"disabled"}/><button className="softBtn" onClick={()=>edit(a)}>ویرایش</button><button className="softBtn" onClick={()=>toggle(a)}>{a.enabled?"خاموش":"فعال"}</button></div></div>)}{!items.length&&<Empty/>}</div></div><div className="card"><div className="cardHead"><div><h3>{form.id?"ویرایش هشدار":"هشدار جدید"}</h3><p>برای بازارهای Spot متصل</p></div>{form.id&&<button className="softBtn" onClick={()=>{setForm(blank);setQ("")}}>انصراف</button>}</div><div className="formGrid oneCol"><div className="field"><label>عنوان</label><input value={form.title} onChange={e=>setForm({...form,title:e.target.value})}/></div><div className="field"><label>جست‌وجوی بازار</label><input value={q} onChange={e=>setQ(e.target.value)} placeholder="BTC"/><select value={form.market} onChange={e=>setForm({...form,market:e.target.value})}><option value="">انتخاب بازار</option>{markets.map(m=><option key={m.id} value={m.id}>{m.base_asset} · {m.exchange_name}</option>)}</select></div><div className="field"><label>نوع</label><select value={form.kind} onChange={e=>setForm({...form,kind:e.target.value})}><option value="price">رسیدن به قیمت</option><option value="rise">افزایش درصدی</option><option value="fall">کاهش درصدی</option></select></div><div className="field"><label>جهت عبور</label><select value={form.direction} onChange={e=>setForm({...form,direction:e.target.value})}><option value="above">بالاتر یا مساوی</option><option value="below">پایین‌تر یا مساوی</option></select></div><div className="field"><label>Threshold</label><input value={form.threshold} onChange={e=>setForm({...form,threshold:e.target.value})}/></div><div className="field"><label>Cooldown (ثانیه)</label><input value={form.cooldown_seconds} onChange={e=>setForm({...form,cooldown_seconds:e.target.value})}/></div><label className="confirmLine"><input type="checkbox" checked={form.repeat} onChange={e=>setForm({...form,repeat:e.target.checked})}/><span>هشدار تکرارشونده</span></label><button className="primary fullBtn" onClick={()=>save()}>{form.id?"ذخیره تغییرات":"ذخیره هشدار"}</button></div></div></div><div className="card sectionGap"><div className="cardHead"><div><h3>اعلان‌ها</h3><p>آخرین اعلان‌های داخل برنامه</p></div><button className="iconBtn" onClick={load}><RefreshCw size={17}/></button></div><div className="simpleList">{notes.map(n=><div key={n.id} className={n.read?"mutedRow":""}><div><b>{n.title}</b><span>{n.body}</span></div>{n.read?<span className="pill">خوانده‌شده</span>:<button className="softBtn" onClick={()=>markRead(n.id)}>خواندم</button>}</div>)}{!notes.length&&<Empty/>}</div></div></>}
function Reports({decimals}){const [period,setPeriod]=useState("month");const [data,setData]=useState(null);useEffect(()=>{api(`/api/v1/reports/?period=${period}&group=total`).then(setData)},[period]);const net=(data?.rows||[]).reduce((s,r)=>s+num(r.net_realized),0);return <div className="card"><div className="cardHead"><div><h3>گزارش عملکرد</h3><p>سود/زیان تحقق‌یافته و هزینه‌ها</p></div><div className="row gap"><select className="smallSelect" value={period} onChange={e=>setPeriod(e.target.value)}><option value="day">روز</option><option value="week">هفته</option><option value="month">ماه</option></select><a className="softBtn" href={BASE+`/reports/export.csv?period=${period}&group=total`}>CSV</a></div></div><div className="metricGrid reportMetrics"><Metric icon={TrendingUp} label="خالص" value={`${fmt(net,decimals)} USDT`} hint={period}/><Metric icon={ArrowLeftRight} label="معاملات" value={(data?.rows||[]).reduce((s,r)=>s+num(r.trades),0)} hint="کل"/><Metric icon={CircleDollarSign} label="کارمزد" value={fmt((data?.rows||[]).reduce((s,r)=>s+num(r.fees),0),decimals)} hint="USDT"/></div><div className="tableScroll"><table><thead><tr><th>بازه</th><th>معاملات</th><th>برد</th><th>باخت</th><th>Gross</th><th>Fee</th><th>Net</th></tr></thead><tbody>{(data?.rows||[]).map((r,i)=><tr key={i}><td>{dt(r.period_start)}</td><td>{r.trades}</td><td>{r.wins}</td><td>{r.losses}</td><td>{fmt(r.gross_realized,decimals)}</td><td>{fmt(r.fees,decimals)}</td><td className={num(r.net_realized)>=0?"up":"down"}>{fmt(r.net_realized,decimals)}</td></tr>)}</tbody></table></div></div>}

function Operations({notify}){const [data,setData]=useState(null);const [engine,setEngine]=useState(null);const [host,setHost]=useState(null);const [deploy,setDeploy]=useState(null);const load=()=>Promise.allSettled([api("/api/v1/operations/health/"),api("/api/v1/engine/readiness/"),api("/api/v1/operations/host-capabilities/"),api("/api/v1/deployment/readiness/")]).then(([a,b,c,d])=>{if(a.value)setData(a.value);if(b.value)setEngine(b.value);if(c.value)setHost(c.value);if(d.value)setDeploy(d.value)});useEffect(()=>{load();const t=setInterval(load,30000);return()=>clearInterval(t)},[]);const workers=Array.isArray(data?.workers)?data.workers:Object.entries(data?.workers||{}).map(([queue,v])=>({queue,...(typeof v==="object"?v:{value:v})}));const control=async(a,action)=>{try{await api(`/api/v1/operations/accounts/${a.id}/control/`,{method:"POST",body:{action,version:a.version,confirmed:true}});notify(action==="reconcile"?"تطبیق حساب در صف قرار گرفت":action==="pause"?"ورود جدید متوقف شد":"ورود جدید فعال شد");setTimeout(load,1200)}catch(e){notify(e.message)}};return <div className="operationsGrid"><div className="card"><div className="cardHead"><div><h3>کنترل حساب‌های واقعی</h3><p>توقف ورود جدید، تطبیق و ادامه امن</p></div><button className="iconBtn" onClick={load}><RefreshCw size={17}/></button></div><div className="simpleList">{(data?.accounts||[]).map(a=><div key={a.id}><div><b>{a.exchange} · {a.label}</b><span>Sync: {dt(a.last_sync_at)} · تطبیق: {dt(a.last_reconciled_at)}</span></div><div className="row gap"><span className={a.paused?"status warn":"status ok"}>{a.paused?"ورود متوقف":"ورود فعال"}</span><button className="softBtn" onClick={()=>control(a,"reconcile")}>تطبیق</button><button className="softBtn" onClick={()=>control(a,a.paused?"resume":"pause")}>{a.paused?"ادامه":"توقف ورود"}</button></div></div>)}{!(data?.accounts||[]).length&&<Empty/>}</div></div><div className="card"><div className="cardHead"><div><h3>Workerها</h3><p>صف‌های مستقل CryptoSniper</p></div></div><div className="simpleList">{workers.map((v,i)=><div key={v.queue||i}><div><b>{v.queue||"worker"}</b><span>آخرین حضور: {dt(v.seen_at)} · lag {v.lag_seconds??"—"}</span></div><span className={v.fresh===false?"status danger":"status ok"}>{v.fresh===false?"قدیمی":"فعال"}</span></div>)}</div></div>{(data?.unresolved_issues||[]).length>0&&<div className="card"><div className="cardHead"><div><h3>موارد نیازمند بررسی</h3><p>اختلاف‌های باز ثبت‌شده توسط موتور تطبیق</p></div></div><div className="simpleList">{data.unresolved_issues.map(x=><div key={x.id}><div><b>{x.account}</b><span>{x.code} · {x.key}</span></div><small>{dt(x.created_at)}</small></div>)}</div></div>}<div className="card"><div className="cardHead"><div><h3>آمادگی موتور</h3><p>وضعیت سرویس‌ها و قفل‌های ایمنی</p></div></div><pre className="jsonBox">{JSON.stringify(engine,null,2)}</pre></div><div className="card"><div className="cardHead"><div><h3>قابلیت‌های سرور</h3><p>توانمندی‌های Host و وابستگی‌ها</p></div></div><pre className="jsonBox">{JSON.stringify(host,null,2)}</pre></div><div className="card"><div className="cardHead"><div><h3>آمادگی استقرار</h3><p>چک نهایی اجرای Production</p></div></div><pre className="jsonBox">{JSON.stringify(deploy,null,2)}</pre></div></div>}
function SettingsPage({decimals,setDecimals,notify}){
  const [tab,setTab]=useState("profile");
  const [profile,setProfile]=useState(null);
  const [prefs,setPrefs]=useState(null);
  const [sources,setSources]=useState([]);
  const [notePrefs,setNotePrefs]=useState(null);
  const [security,setSecurity]=useState({sessions:[],audit:[]});
  const [favoriteMap,setFavoriteMap]=useState({});
  const [exchangeAccounts,setExchangeAccounts]=useState([]);
  const [favExchange,setFavExchange]=useState("");
  const [favSearch,setFavSearch]=useState("");
  const [favMarkets,setFavMarkets]=useState([]);

  const load=()=>Promise.allSettled([
    api("/api/v1/me/"),
    api("/api/v1/me/trading-preferences/"),
    api("/api/v1/ui/signal-sources/"),
    api("/api/v1/ui/notification-preferences/"),
    api("/api/v1/ui/security/"),
    api("/api/v1/ui/favorites/"),
    api("/api/v1/ui/bootstrap/")
  ]).then(([a,b,c,d,e,f,g])=>{
    if(a.value)setProfile(a.value.profile);
    if(b.value)setPrefs(b.value.trading_preferences);
    if(c.value)setSources(c.value.sources||[]);
    if(d.value)setNotePrefs(d.value.preferences);
    if(e.value)setSecurity(e.value);
    if(f.value)setFavoriteMap(f.value.by_exchange||{});
    if(g.value){
      const accounts=g.value.accounts||[];
      setExchangeAccounts(accounts);
      if(!favExchange&&accounts[0])setFavExchange(accounts[0].exchange);
    }
  });
  useEffect(()=>{load()},[]);

  useEffect(()=>{
    const account=exchangeAccounts.find(a=>a.exchange===favExchange);
    if(!account){setFavMarkets([]);return}
    api("/api/v1/exchange-accounts/"+account.id+"/markets/").then(d=>setFavMarkets(d.markets||[])).catch(()=>setFavMarkets([]));
  },[favExchange,exchangeAccounts.length]);

  const saveProfile=async()=>{try{const d=await api("/api/v1/me/",{method:"PATCH",body:{display_name:profile.display_name,email:profile.email,timezone:profile.timezone,base_currency:profile.base_currency,theme:profile.theme}});setProfile(d.profile);notify("پروفایل ذخیره شد")}catch(e){notify(e.message)}};
  const savePrefs=async()=>{try{
    const body={
      default_order_amount:String(prefs.default_order_amount||"50"),
      default_market:prefs.default_market,
      tp1_percent:String(prefs.tp_distribution?.[0]||"10"),
      tp2_percent:String(prefs.tp_distribution?.[1]||"10"),
      tp3_percent:String(prefs.tp_distribution?.[2]||"80"),
      trailing_sl_enabled:!!prefs.trailing_sl_enabled,
      trailing_tp_enabled:!!prefs.trailing_tp_enabled,
      trailing_trigger:prefs.trailing_trigger||"tp1",
      trailing_distance_percent:String(prefs.trailing_distance_percent||"1")
    };
    const d=await api("/api/v1/me/trading-preferences/",{method:"PATCH",body});
    setPrefs(d.trading_preferences);
    notify("پیش‌فرض‌های معامله ذخیره شد");
  }catch(e){notify(e.message)}};
  const toggleSource=async x=>{try{const d=await api("/api/v1/ui/signal-sources/",{method:"POST",body:{id:x.id,enabled:!x.enabled}});setSources(d.sources||[])}catch(e){notify(e.message)}};
  const saveNotePrefs=async next=>{try{const d=await api("/api/v1/ui/notification-preferences/",{method:"PATCH",body:next});setNotePrefs(d.preferences);notify("تنظیم اعلان ذخیره شد")}catch(e){notify(e.message)}};
  const revokeSession=async id=>{try{const d=await api("/api/v1/ui/security/",{method:"POST",body:{action:"revoke_session",session_id:id}});setSecurity(d);notify("نشست بسته شد")}catch(e){notify(e.message)}};

  const favorites=favoriteMap[favExchange]||[];
  const filteredFavMarkets=favMarkets.filter(m=>!favSearch.trim()||m.base.toLowerCase().includes(favSearch.trim().toLowerCase())||m.symbol.toLowerCase().includes(favSearch.trim().toLowerCase()));
  const saveFavorites=async symbols=>{try{const d=await api("/api/v1/ui/favorites/",{method:"POST",body:{exchange:favExchange,symbols}});setFavoriteMap({...favoriteMap,[favExchange]:d.symbols||[]});notify("ارزهای منتخب ذخیره شدند")}catch(e){notify(e.message)}};
  const toggleFavorite=symbol=>saveFavorites(favorites.includes(symbol)?favorites.filter(x=>x!==symbol):[...favorites,symbol]);

  return <div className="settingsLayout">
    <div className="settingsNav card">{[["profile","پروفایل و نمایش"],["trading","پیش‌فرض معامله"],["favorites","ارزهای منتخب"],["sources","منابع سیگنال"],["notifications","اعلان‌ها"],["security","امنیت و نشست‌ها"]].map(([id,label])=><button type="button" key={id} className={tab===id?"active":""} onClick={()=>setTab(id)}>{label}</button>)}</div>
    <div className="card">
      {tab==="profile"&&<><div className="cardHead"><div><h3>پروفایل و نمایش</h3><p>رابط فارسی و تنظیمات حساب</p></div></div>{profile&&<div className="formGrid"><div className="field"><label>نام نمایشی</label><input value={profile.display_name||""} onChange={e=>setProfile({...profile,display_name:e.target.value})}/></div><div className="field"><label>ایمیل</label><input value={profile.email||""} onChange={e=>setProfile({...profile,email:e.target.value})}/></div><div className="field"><label>منطقه زمانی</label><input value={profile.timezone||""} onChange={e=>setProfile({...profile,timezone:e.target.value})}/></div><div className="field"><label>ارز پایه</label><input value={profile.base_currency||"USDT"} onChange={e=>setProfile({...profile,base_currency:e.target.value})}/></div></div>}<div className="settingRow"><div><b>تعداد اعشار نمایشی</b><span>دقت موتور داخلی حفظ می‌شود.</span></div><select value={decimals} onChange={e=>setDecimals(Number(e.target.value))}><option value="0">بدون اعشار</option><option value="1">۱ رقم</option><option value="2">۲ رقم</option><option value="4">۴ رقم</option><option value="6">۶ رقم</option><option value="8">۸ رقم</option></select></div><div className="submitRow"><button type="button" className="primary" onClick={saveProfile}><Save size={17}/> ذخیره پروفایل</button></div></>}

      {tab==="trading"&&prefs&&<><div className="cardHead"><div><h3>پیش‌فرض‌های معامله</h3><p>مقادیر پیش‌فرض صحیح؛ Trailing و Trailing SL</p></div></div><div className="formGrid"><div className="field"><label>مبلغ پیش‌فرض USDT</label><input type="number" step="1" min="0" value={prefs.default_order_amount} onChange={e=>setPrefs({...prefs,default_order_amount:e.target.value.replace(/[^0-9]/g,"")})}/></div><div className="field"><label>بازار پیش‌فرض</label><select value={prefs.default_market} onChange={e=>setPrefs({...prefs,default_market:e.target.value})}><option value="spot">Spot</option><option value="margin">Margin</option></select></div><div className="field"><label>سهم TP1 ٪</label><input type="number" step="1" min="0" value={prefs.tp_distribution?.[0]||"10"} onChange={e=>{const a=[...(prefs.tp_distribution||["10","10","80"])];a[0]=e.target.value.replace(/[^0-9]/g,"");setPrefs({...prefs,tp_distribution:a})}}/></div><div className="field"><label>سهم TP2 ٪</label><input type="number" step="1" min="0" value={prefs.tp_distribution?.[1]||"10"} onChange={e=>{const a=[...(prefs.tp_distribution||["10","10","80"])];a[1]=e.target.value.replace(/[^0-9]/g,"");setPrefs({...prefs,tp_distribution:a})}}/></div><div className="field"><label>سهم TP3 ٪</label><input type="number" step="1" min="0" value={prefs.tp_distribution?.[2]||"80"} onChange={e=>{const a=[...(prefs.tp_distribution||["10","10","80"])];a[2]=e.target.value.replace(/[^0-9]/g,"");setPrefs({...prefs,tp_distribution:a})}}/></div><div className="field"><label>فاصله Trailing ٪</label><input type="number" step="1" min="1" max="99" value={prefs.trailing_distance_percent||"1"} onChange={e=>setPrefs({...prefs,trailing_distance_percent:e.target.value.replace(/[^0-9]/g,"")})}/></div><div className="field"><label>شروع Trailing</label><select value={prefs.trailing_trigger||"tp1"} onChange={e=>setPrefs({...prefs,trailing_trigger:e.target.value})}><option value="tp1">TP1</option><option value="tp2">TP2</option><option value="tp3">TP3</option></select></div><label className="toggleCard"><input type="checkbox" checked={!!prefs.trailing_tp_enabled} onChange={e=>setPrefs({...prefs,trailing_tp_enabled:e.target.checked})}/><div><b>Trailing</b><span>تریلینگ درصدی؛ شروع پیش‌فرض TP1</span></div></label><label className="toggleCard"><input type="checkbox" checked={!!prefs.trailing_sl_enabled} onChange={e=>setPrefs({...prefs,trailing_sl_enabled:e.target.checked})}/><div><b>Trailing SL</b><span>با رسیدن TP1، Stop یک‌بار به Entry منتقل می‌شود.</span></div></label></div><div className="submitRow"><button type="button" className="primary" onClick={savePrefs}><Save size={17}/> ذخیره پیش‌فرض‌ها</button></div></>}

      {tab==="favorites"&&<><div className="cardHead"><div><h3>ارزهای منتخب هر صرافی</h3><p>این ارزها در انتخاب بازار معامله جدید بالاتر از بقیه نمایش داده می‌شوند.</p></div></div><div className="formGrid"><div className="field"><label>صرافی</label><select value={favExchange} onChange={e=>{setFavExchange(e.target.value);setFavSearch("")}}>{Array.from(new Map(exchangeAccounts.map(a=>[a.exchange,a])).values()).map(a=><option key={a.exchange} value={a.exchange}>{a.exchange_name}</option>)}</select></div><div className="field"><label>جست‌وجوی ارز</label><div className="searchBox compact"><Search size={16}/><input value={favSearch} onChange={e=>setFavSearch(e.target.value)} placeholder="BTC، ETH، SOL…"/></div></div></div><div className="favoriteList">{favorites.map((symbol,index)=><div className="favoriteRow" key={symbol}><GripVertical size={18}/><span className="coinIcon">{symbol[0]}</span><b>{symbol}</b><span className="muted">اولویت {index+1}</span><button type="button" className="iconBtn" onClick={()=>toggleFavorite(symbol)}><X size={16}/></button></div>)}</div><div className="marketList favMarketList">{filteredFavMarkets.slice(0,80).map(m=><div className="marketRow" key={m.id}><div><span className="coinIcon">{m.base[0]}</span><b>{m.base}</b><span className="pill">{m.market_type}</span></div><span>{m.symbol}</span><button type="button" className={favorites.includes(m.base)?"softBtn active":"softBtn"} onClick={()=>toggleFavorite(m.base)}><Star size={16}/>{favorites.includes(m.base)?" منتخب":" افزودن"}</button></div>)}</div></>}

      {tab==="sources"&&<><div className="cardHead"><div><h3>منابع سیگنال</h3><p>Telegram از صفحه Telegram مدیریت می‌شود</p></div></div><div className="simpleList">{sources.map(x=><div key={x.id}><div><b>{x.name}</b><span>{x.method}</span></div>{x.method==="telegram"?<span className="pill">مدیریت در Telegram</span>:<button type="button" className={x.enabled?"softBtn":"primary"} onClick={()=>toggleSource(x)}>{x.enabled?"غیرفعال کردن":"فعال کردن"}</button>}</div>)}</div></>}

      {tab==="notifications"&&notePrefs&&<><div className="cardHead"><div><h3>تنظیم اعلان‌ها</h3><p>نحوه دریافت هشدارهای CryptoSniper</p></div></div><div className="settingRow"><div><b>اعلان داخل برنامه</b><span>نمایش در مرکز اعلان‌ها</span></div><input type="checkbox" checked={!!notePrefs.in_app} onChange={e=>saveNotePrefs({...notePrefs,in_app:e.target.checked})}/></div><div className="settingRow"><div><b>اعلان مرورگر</b><span>در صورت اجازه مرورگر</span></div><input type="checkbox" checked={!!notePrefs.browser} onChange={e=>saveNotePrefs({...notePrefs,browser:e.target.checked})}/></div></>}

      {tab==="security"&&<><div className="cardHead"><div><h3>امنیت و نشست‌ها</h3><p>نشست‌های فعال و Audit اخیر</p></div></div><div className="sectionTitle">نشست‌ها</div><div className="simpleList">{(security.sessions||[]).map(x=><div key={x.id}><div><b>{x.current?"این دستگاه":(x.label||("Session #"+x.id))}</b><span>{"آخرین فعالیت: "+dt(x.last_seen_at)+" · انقضا: "+dt(x.expires_at)}</span></div>{x.current?<span className="status ok">جاری</span>:<button type="button" className="softBtn" disabled={!x.valid} onClick={()=>revokeSession(x.id)}>بستن نشست</button>}</div>)}</div><div className="sectionTitle">Audit اخیر</div><div className="auditList">{(security.audit||[]).slice(0,50).map(x=><div key={x.id}><b>{x.event_type}</b><span>{dt(x.created_at)}</span><code>{JSON.stringify(x.metadata)}</code></div>)}</div></>}
    </div>
  </div>
}

function StepUpModal({onClose,onSuccess,notify}){const [password,setPassword]=useState("");const [busy,setBusy]=useState(false);const submit=async()=>{try{setBusy(true);await api("/api/v1/security/step-up/",{method:"POST",body:{password}});notify("تأیید امنیتی برای ۱۰ دقیقه فعال شد");if(onSuccess)await onSuccess();else onClose()}catch(e){notify(e.message)}finally{setBusy(false)}};return <Modal title="تأیید عملیات حساس" onClose={onClose}><div className="formGrid oneCol"><div className="securityNote"><KeyRound size={18}/><div><b>رمز عبور حساب CryptoSniper</b><span>پس از تأیید، عملیات قبلی به‌صورت خودکار ادامه پیدا می‌کند.</span></div></div><div className="field"><label>رمز عبور</label><input autoFocus type="password" value={password} onChange={e=>setPassword(e.target.value)} onKeyDown={e=>e.key==="Enter"&&submit()}/></div><button type="button" className="primary fullBtn" disabled={busy} onClick={submit}>تأیید</button></div></Modal>}
function Modal({title,onClose,children}){return <div className="drawerMask" onClick={onClose}><div className="modal" onClick={e=>e.stopPropagation()}><div className="cardHead"><h3>{title}</h3><button className="iconBtn" onClick={onClose}><X size={18}/></button></div><div className="modalBody">{children}</div></div></div>}

createRoot(document.getElementById("root")).render(<App/>);
