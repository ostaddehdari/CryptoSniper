from decimal import Decimal
from types import SimpleNamespace

from django.core.cache import cache

from .models import PerformanceAggregate, ReportRefreshState

ZERO = Decimal(0)


def report_dataset(user, cleaned):
    period = cleaned.get("period") or "day"
    group = cleaned.get("group") or "total"
    state = ReportRefreshState.objects.filter(owner=user).first()
    cache_key = (
        f"reports:v1:{user.pk}:{state.built_version if state else 0}:"
        f"{period}:{group}:{cleaned.get('date_from')}:{cleaned.get('date_to')}"
    )
    cached = None
    if state and state.dirty_at is None:
        try:
            cached = cache.get(cache_key)
        except Exception:  # Cache failure must not hide financial reports.
            cached = None
    if cached is not None:
        cached["rows"] = [SimpleNamespace(**row) for row in cached["rows"]]
        return cached
    query = PerformanceAggregate.objects.filter(
        owner=user, timezone=user.timezone, period_kind=period, dimension_kind=group
    )
    if cleaned.get("date_from"):
        query = query.filter(period_start__gte=cleaned["date_from"])
    if cleaned.get("date_to"):
        query = query.filter(period_start__lte=cleaned["date_to"])
    rows = list(query.order_by("period_start", "dimension_value", "currency"))
    total = {
        "trade_count": sum(row.trade_count for row in rows),
        "unknown_count": sum(row.unknown_count for row in rows),
        "wins": sum(row.wins for row in rows),
        "losses": sum(row.losses for row in rows),
        "breakeven": sum(row.breakeven for row in rows),
        "gross_realized": sum((row.gross_realized for row in rows), ZERO),
        "net_realized": sum((row.net_realized for row in rows), ZERO),
        "fees": sum((row.fees for row in rows), ZERO),
        "margin_interest": sum((row.margin_interest for row in rows), ZERO),
    }
    decisive = total["wins"] + total["losses"]
    total["win_rate"] = Decimal(total["wins"]) / Decimal(decisive) * 100 if decisive else None
    maximum = max((abs(row.net_realized) for row in rows), default=ZERO)
    for row in rows:
        row.bar_percent = int(abs(row.net_realized) / maximum * 100) if maximum else 0
        row.bar_sign = "positive" if row.net_realized >= 0 else "negative"
        row.drill_query = ""
        if group == "coin":
            row.drill_query = f"coin={row.dimension_value}"
        elif group == "source":
            row.drill_query = f"source={row.dimension_value}"
        elif group == "exchange":
            row.drill_query = f"exchange={row.dimension_value}"
    result = {
        "rows": rows,
        "total": total,
        "period": period,
        "group": group,
        "latest": max((row.updated_at for row in rows), default=None),
    }
    if state and state.dirty_at is None:
        payload = {
            **result,
            "rows": [
                {
                    key: getattr(row, key)
                    for key in (
                        "period_start",
                        "dimension_value",
                        "currency",
                        "trade_count",
                        "unknown_count",
                        "wins",
                        "losses",
                        "breakeven",
                        "gross_realized",
                        "net_realized",
                        "fees",
                        "margin_interest",
                        "duration_seconds",
                        "updated_at",
                        "bar_percent",
                        "bar_sign",
                        "drill_query",
                    )
                }
                for row in rows
            ],
        }
        try:
            cache.set(cache_key, payload, 120)
        except Exception:
            pass
    return result
