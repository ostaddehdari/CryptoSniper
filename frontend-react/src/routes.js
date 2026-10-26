// Old bookmarks remain usable; unknown routes recover to a working dashboard.
const pages = new Set(["dashboard","trades","manual","smart","inbox","exchanges",
  "telegram","alerts","reports","operations","settings","plans","wallets","watchlist"]);
const aliases = {overview:"dashboard",newtrade:"manual",system:"operations"};
export function resolvePage(raw = "", initial = "dashboard") {
  const page = String(raw || initial).replace(/^#?\/?/, "").split("?")[0];
  const resolved = aliases[page] || page;
  return pages.has(resolved) ? resolved : "dashboard";
}
