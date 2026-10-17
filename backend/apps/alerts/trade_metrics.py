"""Explicit Paper profit basis: realized + marked remainder - cost - all fees.

Spot Paper has no borrowing/interest. Unsupported Margin/live basis is never zero-filled.
"""

from decimal import Decimal


def trade_metric(alert, price):
    trade = alert.trade
    if not trade or trade.mode != "paper" or trade.market.market_type != "spot":
        return None, {"unavailable": "unsupported_profit_or_trade_basis"}
    position = getattr(trade, "position", None)
    protection = getattr(trade, "protection", None)
    if not position or position.quantity <= 0 or not protection:
        return None, {"unavailable": "missing_position"}
    if alert.kind == "entry_change":
        return (price - position.average_entry) / position.average_entry * 100, {
            "unit": "percent",
            "entry": str(position.average_entry),
        }
    if alert.kind == "profit":
        rate = trade.market.taker_fee
        if rate is None:
            return None, {"unavailable": "unknown_exit_fee"}
        entries = list(trade.orders.prefetch_related("fills"))
        cost = sum(
            (f.quantity * f.price for order in entries for f in order.fills.all()), Decimal(0)
        )
        proceeds = sum((f.quantity * f.price for f in trade.exit_fills.all()), Decimal(0))
        if cost <= 0:
            return None, {"unavailable": "entry_cost"}
        projected_exit_fee = position.quantity * price * rate
        net = proceeds + position.quantity * price - cost - position.total_fees - projected_exit_fee
        return net / cost * 100, {
            "unit": "percent",
            "denominator": "actual_entry_notional",
            "entry_cost": str(cost),
            "realized_proceeds": str(proceeds),
            "paid_fees": str(position.total_fees),
            "estimated_remaining_exit_fee": str(projected_exit_fee),
            "borrow_interest": "0",
            "interest_basis": "spot_paper_no_borrow",
        }
    if alert.kind == "near_sl":
        level = protection.effective_stop
    elif alert.kind == "near_activation":
        if not protection.percentage_enabled or protection.percentage_active:
            return None, {"unavailable": "activation_not_pending"}
        level = protection.trigger_price
    elif alert.kind == "near_stop":
        if not protection.percentage_active:
            return None, {"unavailable": "percentage_not_active"}
        level = protection.effective_stop
    else:
        return None, {"unavailable": "unknown_kind"}
    return abs(price - level) / level * 100, {
        "unit": "distance_percent_of_level",
        "level": str(level),
        "protection_version": protection.version,
    }
