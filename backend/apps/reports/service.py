from decimal import Decimal

from .models import PerformanceAggregate

ZERO = Decimal(0)


def report_dataset(user, cleaned):
    period = cleaned.get("period") or "day"
    group = cleaned.get("group") or "total"
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
    return {
        "rows": rows,
        "total": total,
        "period": period,
        "group": group,
        "latest": max((row.updated_at for row in rows), default=None),
    }
