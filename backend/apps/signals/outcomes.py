"""Conservative chronological TP/SL evaluation over normalized OHLC evidence."""

from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.marketdata.history import fetch_binance_history
from apps.marketdata.models import HistoricalCandle

from .models import Signal, SignalOutcome, TelegramMessage


def evaluate_path(*, side, entry, stop, targets, candles):
    entry, stop = Decimal(str(entry)), Decimal(str(stop))
    targets = [Decimal(str(value)) for value in targets]
    entered_at = stopped_at = None
    hit_count = 0
    last_time = None
    ambiguous = False
    for candle in candles:
        low, high = Decimal(str(candle.low_price)), Decimal(str(candle.high_price))
        last_time = candle.close_time
        if entered_at is None:
            if not low <= entry <= high:
                continue
            entered_at = candle.open_time
            stop_touched = low <= stop if side == "long" else high >= stop
            target_touched = (
                any(high >= value for value in targets)
                if side == "long"
                else any(low <= value for value in targets)
            )
            if stop_touched or target_touched:
                ambiguous = True
                break
            continue
        stop_touched = low <= stop if side == "long" else high >= stop
        newly_hit = sum(
            1
            for value in targets[hit_count:]
            if (high >= value if side == "long" else low <= value)
        )
        if stop_touched and newly_hit:
            ambiguous = True
            break
        if stop_touched:
            stopped_at = candle.open_time
            break
        hit_count += newly_hit
        if hit_count >= len(targets):
            break
    if ambiguous:
        status = SignalOutcome.Status.AMBIGUOUS
    elif stopped_at:
        status = SignalOutcome.Status.STOPPED
    elif targets and hit_count >= len(targets):
        status = SignalOutcome.Status.TARGET
    elif entered_at:
        status = SignalOutcome.Status.OPEN
    elif candles:
        status = SignalOutcome.Status.NOT_TRIGGERED
    else:
        status = SignalOutcome.Status.NO_DATA
    return {
        "status": status,
        "entry_hit_at": entered_at,
        "stop_hit_at": stopped_at,
        "targets_hit": hit_count,
        "last_target_price": targets[hit_count - 1] if hit_count else None,
        "evaluated_until": last_time,
        "evidence": {"candles": len(candles), "ambiguous_same_candle": ambiguous},
    }


def _signal_spec(signal):
    extraction = signal.parsed_payload.get("extraction", signal.parsed_payload)
    symbol = extraction.get("pair")
    entry = extraction.get("entry") or signal.entry_price
    stop = extraction.get("stop_loss") or signal.stop_loss
    targets = extraction.get("execution_targets") or list(
        signal.targets.order_by("position").values_list("price", flat=True)
    )
    side = extraction.get("side") or signal.side
    if not symbol or not entry or not stop or not targets or side not in {"long", "short"}:
        raise ValidationError("سیگنال برای ارزیابی تاریخی کامل نیست.")
    return symbol, entry, stop, targets, side


@shared_task(name="signals.evaluate_historical_signal")
def evaluate_historical_signal(signal_id, *, fetch=True):
    signal = (
        Signal.objects.select_related("raw_signal", "owner")
        .prefetch_related("targets")
        .get(pk=signal_id)
    )
    message = TelegramMessage.objects.filter(raw_signal=signal.raw_signal).first()
    start = message.occurred_at if message and message.occurred_at else signal.created_at
    end = min(timezone.now(), start + timedelta(days=30))
    symbol, entry, stop, targets, side = _signal_spec(signal)
    if fetch:
        fetch_binance_history(symbol, start, end, interval="1h")
    candles = list(
        HistoricalCandle.objects.filter(
            provider="binance_public",
            symbol=symbol.upper(),
            interval="1h",
            open_time__gte=start,
            open_time__lte=end,
        ).order_by("open_time")
    )
    result = evaluate_path(side=side, entry=entry, stop=stop, targets=targets, candles=candles)
    outcome, _ = SignalOutcome.objects.update_or_create(
        signal=signal,
        defaults={
            "owner": signal.owner,
            "provider": "binance_public",
            "symbol": symbol.upper(),
            "interval": "1h",
            "evaluated_from": start,
            **result,
        },
    )
    return {"outcome_id": outcome.pk, "status": outcome.status}
