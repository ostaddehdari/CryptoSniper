from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from apps.signals.models import SignalOutcome
from apps.signals.outcomes import evaluate_path


def candle(at, low, high):
    return SimpleNamespace(
        open_time=at,
        close_time=at + timedelta(hours=1),
        low_price=low,
        high_price=high,
    )


def test_historical_outcome_requires_entry_before_target():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    result = evaluate_path(
        side="long",
        entry="100",
        stop="90",
        targets=["110"],
        candles=[candle(start, "105", "120"), candle(start + timedelta(hours=1), "99", "101")],
    )
    assert result["status"] == SignalOutcome.Status.OPEN
    assert result["targets_hit"] == 0


def test_historical_outcome_marks_same_candle_tp_sl_ambiguous():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    result = evaluate_path(
        side="long",
        entry="100",
        stop="90",
        targets=["110"],
        candles=[candle(start, "99", "101"), candle(start + timedelta(hours=1), "89", "111")],
    )
    assert result["status"] == SignalOutcome.Status.AMBIGUOUS
    assert result["evidence"]["ambiguous_same_candle"] is True


def test_historical_short_path_hits_ordered_targets():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    result = evaluate_path(
        side="short",
        entry="100",
        stop="110",
        targets=["95", "90"],
        candles=[
            candle(start, "99", "101"),
            candle(start + timedelta(hours=1), "94", "99"),
            candle(start + timedelta(hours=2), "89", "96"),
        ],
    )
    assert result["status"] == SignalOutcome.Status.TARGET
    assert result["targets_hit"] == 2
