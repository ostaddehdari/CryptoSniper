"""Shared fill/fee accounting for Dashboard, trade lists and future reports.

All P/L is separated by quote currency and trading mode. Win rate uses fully
closed Paper trades with known net result; zero-result closes are not wins.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Prefetch
from django.utils import timezone

from apps.trading.models import Order, Trade

from .quotes import quotes_for

ZERO = Decimal(0)
ACTIVE = ("queued", "submitting", "partially_filled", "open", "uncertain")


def trade_queryset(owner):
    return (
        Trade.objects.filter(owner=owner)
        .select_related(
            "market__exchange",
            "market__quote_asset",
            "market__base_asset",
            "account",
            "protection",
            "position",
            "signal__source",
            "plan",
        )
        .prefetch_related(
            Prefetch("orders", queryset=Order.objects.prefetch_related("fills")),
            "exit_fills",
            "targets",
        )
    )


def day_bounds(user, now=None):
    zone = ZoneInfo(user.timezone)
    date = (now or timezone.now()).astimezone(zone).date()
    return datetime.combine(date, time.min, zone), datetime.combine(
        date + timedelta(days=1), time.min, zone
    )


def price_for(trade, quotes):
    protection = getattr(trade, "protection", None)
    if protection and protection.paper_scenario:
        if (
            protection.last_tick_at
            and -5 <= (timezone.now() - protection.last_tick_at).total_seconds() <= 55
        ):
            return {
                "price": protection.last_price,
                "observed_at": protection.last_tick_at,
                "source": "paper_scenario",
            }
        return None
    return quotes.get(trade.market_id)


def result_for(trade, quote=None, bounds=None):
    entries = [fill for order in trade.orders.all() for fill in order.fills.all()]
    exits = list(trade.exit_fills.all())
    quantity = sum((f.quantity for f in entries), ZERO)
    cost = sum((f.quantity * f.price for f in entries), ZERO)
    entry_fees = sum((f.fee for f in entries), ZERO)
    exit_qty = sum((f.quantity for f in exits), ZERO)
    exit_fees = sum((f.fee for f in exits), ZERO)
    remaining = quantity - exit_qty
    avg = cost / quantity if quantity else None
    valid = trade.mode == "paper" and trade.market.market_type == "spot" and remaining >= 0
    realized = ZERO
    today_realized = ZERO
    if quantity and valid:
        for fill in exits:
            value = (
                fill.quantity * (fill.price - avg)
                - fill.fee
                - entry_fees * fill.quantity / quantity
            )
            realized += value
            if bounds and bounds[0] <= fill.occurred_at < bounds[1]:
                today_realized += value
    unrealized = None
    if not remaining:
        unrealized = ZERO
    elif valid and quote and trade.market.taker_fee is not None:
        unrealized = (
            remaining * (quote["price"] - avg)
            - entry_fees * remaining / quantity
            - remaining * quote["price"] * trade.market.taker_fee
        )
    closed_at = (
        max((f.occurred_at for f in exits), default=None) if trade.state == "closed" else None
    )
    return {
        "entry_quantity": quantity,
        "remaining": remaining,
        "average_entry": avg,
        "entry_cost": cost,
        "paid_fees": entry_fees + exit_fees,
        "realized": realized if valid else None,
        "today_realized": today_realized,
        "unrealized": unrealized if valid else None,
        "currency": trade.market.quote_asset.symbol,
        "quote": quote,
        "closed_at": closed_at,
        "duration_seconds": max(
            0, int(((closed_at or timezone.now()) - trade.created_at).total_seconds())
        ),
        "profit_percent": (realized + unrealized) / cost * 100
        if valid and cost and unrealized is not None
        else None,
    }


def summarize(user, trades):
    trades = list(trades)
    quotes, cache_ok = quotes_for({t.market.pk: t.market for t in trades}.values())
    bounds = day_bounds(user)
    buckets = {}
    today_count = 0
    for trade in trades:
        trade.stats = result_for(trade, price_for(trade, quotes), bounds)
        if bounds[0] <= trade.created_at < bounds[1]:
            today_count += 1
        key = (trade.mode, trade.stats["currency"])
        bucket = buckets.setdefault(
            key,
            {
                "mode": key[0],
                "currency": key[1],
                "realized": ZERO,
                "today_realized": ZERO,
                "unrealized": ZERO,
                "unpriced_open": 0,
                "closed": 0,
                "wins": 0,
                "win_rate": None,
            },
        )
        if trade.stats["realized"] is not None:
            bucket["realized"] += trade.stats["realized"]
            bucket["today_realized"] += trade.stats["today_realized"]
        if trade.stats["remaining"] > 0:
            if trade.stats["unrealized"] is None:
                bucket["unpriced_open"] += 1
            else:
                bucket["unrealized"] += trade.stats["unrealized"]
        if (
            trade.state == "closed"
            and trade.stats["realized"] is not None
            and trade.stats["entry_quantity"] > 0
            and trade.stats["remaining"] == 0
        ):
            bucket["closed"] += 1
            bucket["wins"] += trade.stats["realized"] > 0
    for bucket in buckets.values():
        bucket["win_rate"] = (
            Decimal(bucket["wins"]) / bucket["closed"] * 100 if bucket["closed"] else None
        )
    return {
        "trades": trades,
        "buckets": list(buckets.values()),
        "today_count": today_count,
        "open_count": sum(t.state in ACTIVE for t in trades),
        "cache_ok": cache_ok,
    }
