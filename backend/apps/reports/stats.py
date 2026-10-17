"""Deterministic Stage15 report statistics built from the shared fill ledger."""

from decimal import Decimal

from apps.portfolio.metrics import ACTIVE, summarize, trade_queryset

BREAKEVEN_EPSILON = Decimal("0.00000001")
ZERO = Decimal(0)


def classify_result(value):
    """Breakeven is a fixed inclusive ±1e-8 amount in the quote currency."""
    if value is None:
        return "unknown"
    if abs(value) <= BREAKEVEN_EPSILON:
        return "breakeven"
    return "win" if value > 0 else "loss"


def report_statistics(user, queryset=None):
    queryset = queryset if queryset is not None else trade_queryset(user)
    summary = summarize(user, queryset)
    buckets = {}
    for trade in summary["trades"]:
        stats = trade.stats
        key = (trade.mode, stats["currency"])
        bucket = buckets.setdefault(
            key,
            {
                "mode": trade.mode,
                "currency": stats["currency"],
                "total_trades": 0,
                "open_trades": 0,
                "closed_trades": 0,
                "evaluated_trades": 0,
                "unknown_trades": 0,
                "wins": 0,
                "losses": 0,
                "breakeven": 0,
                "win_rate": None,
                "average_profit": None,
                "average_loss": None,
                "best_trade": None,
                "worst_trade": None,
                "average_duration_seconds": None,
                "net_realized": ZERO,
                "gross_realized": ZERO,
                "fees": ZERO,
                "margin_interest": ZERO,
            },
        )
        bucket["total_trades"] += 1
        if trade.state in ACTIVE:
            bucket["open_trades"] += 1
        is_closed = (
            trade.state == "closed" and stats["entry_quantity"] > 0 and stats["remaining"] == 0
        )
        if not is_closed:
            continue
        bucket["closed_trades"] += 1
        outcome = classify_result(stats["realized"])
        if outcome == "unknown":
            bucket["unknown_trades"] += 1
            continue
        bucket["evaluated_trades"] += 1
        bucket[{"win": "wins", "loss": "losses"}.get(outcome, outcome)] += 1
        bucket["net_realized"] += stats["realized"]
        bucket["gross_realized"] += stats["gross_realized"]
        bucket["fees"] += stats["paid_fees"]
        bucket["margin_interest"] += stats["margin_interest"]
        bucket.setdefault("_durations", []).append(stats["duration_seconds"])
        bucket.setdefault("_profits", []).append(stats["realized"])
        if outcome == "win":
            bucket.setdefault("_wins", []).append(stats["realized"])
        elif outcome == "loss":
            bucket.setdefault("_losses", []).append(stats["realized"])

    for bucket in buckets.values():
        decisive = bucket["wins"] + bucket["losses"]
        bucket["win_rate"] = Decimal(bucket["wins"]) / Decimal(decisive) * 100 if decisive else None
        profits = bucket.pop("_profits", [])
        wins = bucket.pop("_wins", [])
        losses = bucket.pop("_losses", [])
        durations = bucket.pop("_durations", [])
        bucket["average_profit"] = sum(wins, ZERO) / len(wins) if wins else None
        bucket["average_loss"] = sum(losses, ZERO) / len(losses) if losses else None
        bucket["best_trade"] = max(profits, default=None)
        bucket["worst_trade"] = min(profits, default=None)
        bucket["average_duration_seconds"] = sum(durations) // len(durations) if durations else None
    return {"buckets": list(buckets.values()), "trades": summary["trades"]}
