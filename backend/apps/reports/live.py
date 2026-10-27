"""Realized live Spot finance from confirmed provider receipts only."""

from datetime import UTC, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Prefetch
from django.utils import timezone

from apps.operations.models import LiveExitAttempt, ManagedSpotPosition

ZERO = Decimal(0)


def _window(user, period):
    now = timezone.now().astimezone(ZoneInfo(user.timezone))
    if period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    else:
        period = "month"
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return period, start.astimezone(UTC), now


def live_financial_report(user, period="month"):
    period, start, now = _window(user, period)
    exits = LiveExitAttempt.objects.filter(
        order__updated_at__gte=start, order__filled_amount__gt=0
    ).select_related("order")
    positions = (
        ManagedSpotPosition.objects.filter(
            account__owner=user,
            account__environment="live",
            exits__order__updated_at__gte=start,
            exits__order__filled_amount__gt=0,
        )
        .exclude(account__exchange__adapter_code="simulator")
        .select_related(
            "account__exchange",
            "market__quote_asset",
            "market__base_asset",
            "entry_order",
            "external_policy",
        )
        .prefetch_related(Prefetch("exits", queryset=exits, to_attr="report_exits"))
        .distinct()
    )
    rows = []
    for position in positions:
        filled_exits = [attempt.order for attempt in position.report_exits]
        exited = sum((order.filled_amount for order in filled_exits), ZERO)
        entry_price = (
            position.entry_order.average_price
            if position.entry_order_id and position.entry_order.average_price is not None
            else position.external_policy.entry_price
            if position.external_policy_id
            else None
        )
        proceeds_known = entry_price is not None and all(
            order.average_price is not None for order in filled_exits
        )
        gross = (
            sum((order.filled_amount * order.average_price for order in filled_exits), ZERO)
            - exited * entry_price
            if proceeds_known
            else None
        )
        exit_fees_known = all(order.fee_quote_value is not None for order in filled_exits)
        entry_fee = None
        if (
            position.entry_order_id
            and position.entry_order.fee_quote_value is not None
            and position.acquired > 0
        ):
            entry_fee = position.entry_order.fee_quote_value * exited / position.acquired
        fees = (
            entry_fee + sum((order.fee_quote_value for order in filled_exits), ZERO)
            if entry_fee is not None and exit_fees_known
            else None
        )
        net = gross - fees if gross is not None and fees is not None else None
        rows.append(
            {
                "position_id": position.pk,
                "symbol": position.market.symbol,
                "exchange": position.account.exchange.name,
                "currency": position.market.quote_asset.symbol,
                "exited_amount": exited,
                "gross_realized": gross,
                "fees": fees,
                "net_realized": net,
                "unknown_reason": "" if net is not None else "missing_exact_fill_or_fee",
                "updated_at": max(order.updated_at for order in filled_exits),
            }
        )
    known_rows = [row for row in rows if row["net_realized"] is not None]
    currencies = sorted({row["currency"] for row in rows})
    unknown_count = len(rows) - len(known_rows)
    total = {
        "trade_count": len(rows),
        "known_count": len(known_rows),
        "unknown_count": unknown_count,
        "currency": currencies[0] if len(currencies) == 1 else None,
        "gross_realized": sum((row["gross_realized"] for row in known_rows), ZERO),
        "fees": sum((row["fees"] for row in known_rows), ZERO),
        "known_net_realized": sum((row["net_realized"] for row in known_rows), ZERO),
        "net_realized": (
            sum((row["net_realized"] for row in known_rows), ZERO)
            if not unknown_count and len(currencies) <= 1
            else None
        ),
    }
    return {
        "mode": "live",
        "source": "confirmed_exchange_receipts",
        "period": period,
        "period_start": start,
        "generated_at": now,
        "total": total,
        "rows": rows,
    }
