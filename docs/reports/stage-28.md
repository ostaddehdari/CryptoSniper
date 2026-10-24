# Stage 28 — Live Charts, Archive Views and Provider Refresh

## Scope

Stage 28 upgrades the React control center used at `/cryptosniper/app/` without changing the live-trading safety boundary.

### Inbox

- Selected signals render a live candlestick chart.
- Entry, TP1–TP3 and Stop Loss are rendered as price guides.
- The first candle that touches Entry/TP/SL is annotated with a vertical event line and a colored circular marker.
- Signal detail includes a schematic TP/SL roadmap.
- Signal list supports card and table views.
- Active / all / archive filters are available.
- Delete is non-destructive: it archives. Restore is supported.
- Terminal evaluated outcomes (target, stopped, expired) are automatically moved to archive.

### New Trade

- The chart is rendered as candlesticks instead of a close-price polyline.
- Timeframes: 1m, 5m, 15m, 1h and 4h.
- Recent history is backfilled on demand from the bounded public historical feed.
- Live price updates the visible current candle.
- A toggle can overlay levels from an already-open managed trade for the selected market.

### Trades

- Internal and external rows support active / all / archive views.
- Archive never cancels, closes or alters an exchange order.
- Trade drawers include a market chart and management levels.
- Refresh triggers exchange-account sync and provider observation refresh, then reloads the list.

### Provider refresh

- Manual account sync now also refreshes external open orders/history for readable LIVE accounts.
- Bitunix observation candidates include active internal markets and recently observed symbols in addition to positive-balance assets.
- Provider read failures are surfaced in account diagnostics instead of being silently discarded.

## Safety

- Archive is visibility-only.
- Historical chart fetches are bounded and cached.
- External observations remain read-only unless the operator explicitly adopts a trade.
- No withdrawal permission is introduced.
- Live order submission remains behind the existing step-up and provider safety checks.
