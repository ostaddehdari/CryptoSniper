"""Periodic public-feed refresh, bounded and round-robin across watched markets."""
import logging

from celery import shared_task
from django.core.cache import cache

from apps.exchanges.models import ExchangeMarket, UserExchangeAccount

from .feeds import get_quote, refresh_quote
from .models import WatchlistItem

logger = logging.getLogger(__name__)
BATCH_SIZE = 2


@shared_task(name="marketdata.refresh_market", acks_late=True, time_limit=40)
def refresh_market(market_id):
    market = ExchangeMarket.objects.select_related("exchange").get(pk=market_id)
    return refresh_quote(market)


@shared_task(name="marketdata.refresh_watchlists", acks_late=True, time_limit=40)
def refresh_watchlists():
    # Public data only; no API secret or account-specific provider request is made.
    allowed = set(
        UserExchangeAccount.objects.filter(
            status__in=("connected", "restricted"), permissions__can_read=True
        ).values_list("owner_id", "exchange_id")
    )
    rows = WatchlistItem.objects.order_by("market_id").values_list(
        "market_id", "watchlist__owner_id", "market__exchange_id"
    ).distinct()[:2000]
    ids = sorted({market_id for market_id, owner_id, exchange_id in rows
                  if (owner_id, exchange_id) in allowed})
    if not ids:
        return {"refreshed": 0, "available": 0}
    cursor = int(cache.get("marketdata:v1:cursor", 0)) % len(ids)
    chunk = [ids[(cursor + step) % len(ids)] for step in range(min(BATCH_SIZE, len(ids)))]
    cache.set("marketdata:v1:cursor", (cursor + len(chunk)) % len(ids), 3600)
    count = 0
    for market in ExchangeMarket.objects.select_related("exchange").filter(pk__in=chunk):
        if get_quote(market) and not get_quote(market)["stale"]:
            continue
        outcome = refresh_quote(market)
        if outcome["status"] == "ok":
            count += 1
    logger.info("Public market refresh complete", extra={"market_count": count})
    return {"refreshed": count, "available": len(ids)}
