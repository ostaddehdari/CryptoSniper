# CryptoSniper Stage25 React Cornix Rebuild

## Source of truth

The approved visual baseline is the React workspace introduced by commit
`e0bc50bd090736d99e7d82661b30d2b7a5140b05` and preserved on
`stage23-react-live-ui`.

The approved stylesheet blob is byte-locked as:

`565980a9a4a5ba390f09fcc61c5a6ea9a6a82cdd`

Stage25 keeps that visual base unchanged and layers only functional additions in
`frontend-react/src/stage25.css`.

## Primary surface

- `/` -> React workspace
- `/app/` -> React workspace
- `/dashboard/` -> React workspace
- Legacy primary UI routes redirect into the corresponding React route.
- Django templates remain only as compatibility/back-end fallback surfaces.

## Functional integration

- Live USDT/USD and USDT/Toman header ticker.
- Exchange account -> immediate account-scoped market list.
- Live market chart with 1m/5m/15m/1h/4h intervals.
- Signal Entry/TP/SL overlays and lifecycle markers.
- Unified Internal / Live / External trade workspace.
- Signal card/table views with active/archive/all lifecycle.
- Trailing SL: TP1 -> Entry exactly once.
- Trailing TP: selectable start at TP1, TP2 or TP3.
- Default TP split remains 10 / 10 / 80.
- Live exchange writes remain fail-closed by default.

## React build contract

Production does not need Node.js. Release CI builds Vite assets and packages
the generated `backend/static/react/app.js` and `app.css` into the release ZIP.

## Safety

- Existing database, login and encrypted exchange/Telegram credentials are preserved.
- No withdrawal credentials are introduced.
- External trades remain read-only until explicit management handoff.
