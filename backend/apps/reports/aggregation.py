import hashlib
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.portfolio.metrics import summarize, trade_queryset

from .models import PerformanceAggregate
from .stats import classify_result

ZERO = Decimal(0)


def _periods(date):
    return {
        "day": date,
        "week": date - timedelta(days=date.weekday()),
        "month": date.replace(day=1),
    }


def _dimensions(trade):
    source = trade.signal.source.method if trade.signal_id else "manual"
    return {
        ("total", "all"),
        ("coin", trade.market.base_asset.symbol),
        ("exchange", trade.market.exchange.code),
        ("source", source),
    }


def _empty():
    return {
        "trade_count": 0,
        "unknown_count": 0,
        "wins": 0,
        "losses": 0,
        "breakeven": 0,
        "gross_realized": ZERO,
        "net_realized": ZERO,
        "fees": ZERO,
        "margin_interest": ZERO,
        "duration_seconds": 0,
        "trade_ids": [],
    }


@transaction.atomic
def rebuild_user_reports(user_id):
    user = get_user_model().objects.select_for_update().get(pk=user_id)
    zone = ZoneInfo(user.timezone)
    summary = summarize(user, trade_queryset(user).order_by("pk"))
    grouped = {}
    for trade in summary["trades"]:
        stats = trade.stats
        if trade.state != "closed" or stats["closed_at"] is None or stats["remaining"] != 0:
            continue
        local_date = stats["closed_at"].astimezone(zone).date()
        outcome = classify_result(stats["realized"])
        for period_kind, period_start in _periods(local_date).items():
            for dimension_kind, dimension_value in _dimensions(trade):
                key = (
                    period_kind,
                    period_start,
                    dimension_kind,
                    dimension_value,
                    trade.mode,
                    stats["currency"],
                )
                row = grouped.setdefault(key, _empty())
                row["trade_count"] += 1
                row["trade_ids"].append(trade.pk)
                if outcome == "unknown":
                    row["unknown_count"] += 1
                    continue
                row[{"win": "wins", "loss": "losses"}.get(outcome, outcome)] += 1
                row["gross_realized"] += stats["gross_realized"]
                row["net_realized"] += stats["realized"]
                row["fees"] += stats["paid_fees"]
                row["margin_interest"] += stats["margin_interest"]
                row["duration_seconds"] += stats["duration_seconds"]

    kept = []
    for key, values in grouped.items():
        fingerprint = hashlib.sha256(
            (user.timezone + ":" + ",".join(map(str, values.pop("trade_ids")))).encode()
        ).hexdigest()
        identity = {
            "owner": user,
            "timezone": user.timezone,
            "period_kind": key[0],
            "period_start": key[1],
            "dimension_kind": key[2],
            "dimension_value": key[3],
            "mode": key[4],
            "currency": key[5],
        }
        aggregate, _ = PerformanceAggregate.objects.update_or_create(
            **identity, defaults={**values, "source_fingerprint": fingerprint}
        )
        kept.append(aggregate.pk)
    stale = PerformanceAggregate.objects.filter(owner=user)
    if kept:
        stale = stale.exclude(pk__in=kept)
    deleted, _ = stale.delete()
    return {"rows": len(kept), "deleted": deleted}
