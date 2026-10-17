"""Owner-only evidence; arbitrary provider JSON is never sent to the browser."""

from uuid import uuid4

from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404

from apps.portfolio.metrics import summarize, trade_queryset

SAFE_EVENT_KEYS = {
    "id",
    "reason",
    "price",
    "quantity",
    "remaining",
    "state",
    "status",
    "stop",
    "previous_stop",
    "effective_stop",
    "version",
    "coverage",
    "native_stop",
    "final_exit",
    "fill_id",
    "order_id",
    "client_order_id",
    "action_id",
    "code",
    "source",
    "attempt",
    "fee",
    "filled_quantity",
    "feed",
}


def detail_context(user, pk, params):
    trade = get_object_or_404(trade_queryset(user).select_related("signal__raw_signal"), pk=pk)
    summarize(user, [trade])
    page = Paginator(trade.events.order_by("-pk"), 30).get_page(params.get("events"))
    events = []
    for event in page:
        payload = event.payload if isinstance(event.payload, dict) else {}
        event.safe_payload = {
            k: v
            for k, v in payload.items()
            if k in SAFE_EVENT_KEYS and isinstance(v, (str, int, float, bool, type(None)))
        }
        events.append(event)
    return {
        "request_key": str(uuid4()),
        "needs_reconciliation": trade.state in ("uncertain", "submitting", "partially_filled"),
        "recovery_open": trade.account.recoveryissue_set.filter(resolved=False).exists(),
        "execution_snapshot": {
            k: v
            for k, v in trade.snapshot.items()
            if k
            in {
                "entry_price",
                "stop_loss",
                "capital",
                "leverage",
                "side",
                "source",
                "market_type",
                "trailing_sl",
                "percentage_trailing",
                "trailing_distance_percent",
            }
            and isinstance(v, (str, int, bool, type(None)))
        },
        "actions": trade.actions.order_by("-pk")[:10],
        "trade": trade,
        "events": events,
        "event_page": page,
        "orders": trade.orders.all(),
        "position": getattr(trade, "position", None),
        "protection": getattr(trade, "protection", None),
        "targets": trade.targets.all(),
        "exit_fills": trade.exit_fills.all(),
        "nav": "paper",
    }
