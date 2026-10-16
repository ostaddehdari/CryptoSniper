"""Periodic backend-only PAPER price updates, never real exchange orders."""
import logging

from celery import shared_task
from django.utils import timezone

from apps.exchanges.adapters import get_adapter

from .exits_engine import process_paper_price
from .exits_plan import ensure_exits
from .models import Trade

log = logging.getLogger(__name__)


@shared_task(name="trading.monitor_paper_exits")
def monitor_paper_exits():
    ids = list(
        Trade.objects.filter(
            mode="paper", state__in=["open", "partially_filled"],
            account__environment="paper", account__exchange__adapter_code="simulator",
            market__market_type="spot",
        ).order_by("pk").values_list("pk", flat=True)[:100]
    )
    adapter = get_adapter("simulator", credentials={}, environment="paper")
    processed = 0
    for trade_id in ids:
        try:
            protection, _ = ensure_exits(trade_id)
            if protection.paper_scenario:
                continue
            trade = Trade.objects.select_related("market").get(pk=trade_id)
            quote = adapter.fetch_ticker(trade.market.symbol)
            process_paper_price(
                trade_id, price=quote.price, observed_at=quote.observed_at,
                source="simulator",
                event_key=f"sim-{trade_id}-{int(quote.observed_at.timestamp() * 1000000)}",
            )
            processed += 1
        except Exception:
            log.exception("Paper simulator exit check failed", extra={"trade_id": trade_id})
    return {"seen": len(ids), "processed": processed}
