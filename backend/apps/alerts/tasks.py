"""Bounded round-robin alert processing; works without an open browser."""

from celery import shared_task
from django.core.cache import cache

from apps.marketdata.feeds import get_quote
from apps.marketdata.tasks import refresh_market

from .engine import evaluate
from .models import PriceAlert


@shared_task(name="alerts.evaluate", acks_late=True)
def evaluate_alerts():
    cursor = int(cache.get("alerts:cursor", 0))
    queryset = PriceAlert.objects.filter(enabled=True).select_related(
        "market__exchange", "trade__protection"
    )
    batch = list(queryset.filter(pk__gt=cursor).order_by("pk")[:100])
    if not batch:
        batch = list(queryset.order_by("pk")[:100])
    outcomes = []
    for alert in batch:
        if alert.trade and alert.trade.state not in {"open", "partially_filled"}:
            PriceAlert.objects.filter(pk=alert.pk).update(enabled=False, status="trade_closed")
            continue
        if alert.trade and alert.trade.protection.paper_scenario:
            p = alert.trade.protection
            if p.last_tick_at and p.last_price:
                outcomes.append(
                    evaluate(
                        alert.pk,
                        price=p.last_price,
                        observed_at=p.last_tick_at,
                        source="paper_scenario",
                    )
                )
            continue
        quote = get_quote(alert.market)
        if quote and not quote["stale"]:
            from django.utils.dateparse import parse_datetime

            outcomes.append(
                evaluate(
                    alert.pk,
                    price=quote["price"],
                    observed_at=parse_datetime(quote["observed_at"]),
                    source=quote["source"],
                )
            )
        elif cache.add(f"alerts:refresh:{alert.market_id}", "1", timeout=10):
            refresh_market.apply_async(args=[alert.market_id], queue="market_data")
    if batch:
        cache.set("alerts:cursor", batch[-1].pk, 3600)
    return {"seen": len(batch), "fired": outcomes.count("fired")}
