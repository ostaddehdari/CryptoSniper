"""Conservative chronological TP/SL evaluation over normalized OHLC evidence."""

from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.marketdata.history import fetch_binance_history
from apps.marketdata.models import HistoricalCandle

from .models import (
    Signal,
    SignalOutcome,
    TelegramEvaluationJob,
    TelegramMessage,
)


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
        "evidence": {
            "candles": len(candles),
            "ambiguous_same_candle": ambiguous,
            "price_source": "normalized_ohlc",
            "intrabar_order_known": False,
            "profit_claimed": status == SignalOutcome.Status.TARGET,
        },
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
    if end < timezone.now() and result["status"] == SignalOutcome.Status.NOT_TRIGGERED:
        result["status"] = SignalOutcome.Status.EXPIRED
        result["evidence"]["expired_without_entry"] = True
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
    if outcome.status == SignalOutcome.Status.EXPIRED and signal.archived_at is None:
        Signal.objects.filter(pk=signal.pk, archived_at__isnull=True).update(
            archived_at=timezone.now()
        )
    return {"outcome_id": outcome.pk, "status": outcome.status}


def start_channel_evaluation(channel):
    active = channel.evaluation_jobs.filter(status__in=("pending", "running")).first()
    if active:
        return active, False
    total = Signal.objects.filter(source=channel.source).count()
    return (
        TelegramEvaluationJob.objects.create(
            owner=channel.owner,
            channel=channel,
            total_signals=total,
        ),
        True,
    )


@shared_task(name="signals.evaluate_channel_batch")
def evaluate_channel_batch(job_id):
    job = TelegramEvaluationJob.objects.select_related("channel__source").get(pk=job_id)
    if job.status not in {
        TelegramEvaluationJob.Status.PENDING,
        TelegramEvaluationJob.Status.RUNNING,
    }:
        return {"status": job.status}
    job.status = TelegramEvaluationJob.Status.RUNNING
    job.started_at = job.started_at or timezone.now()
    job.save(update_fields=("status", "started_at", "updated_at"))
    signals = list(
        Signal.objects.filter(
            source=job.channel.source,
            pk__gt=job.cursor_signal_id,
        ).order_by("pk")[:1]
    )
    evaluated = skipped = 0
    cursor = job.cursor_signal_id
    for signal in signals:
        cursor = signal.pk
        try:
            evaluate_historical_signal(signal.pk)
            evaluated += 1
        except ValidationError:
            skipped += 1
    job.cursor_signal_id = cursor
    job.evaluated_signals += evaluated
    job.skipped_signals += skipped
    if not signals or job.evaluated_signals + job.skipped_signals >= job.total_signals:
        job.status = TelegramEvaluationJob.Status.COMPLETED
        job.completed_at = timezone.now()
    else:
        job.status = TelegramEvaluationJob.Status.PENDING
    job.save()
    if job.status == TelegramEvaluationJob.Status.PENDING:
        evaluate_channel_batch.apply_async(args=[job.pk], queue="signals")
    return {"status": job.status, "evaluated": evaluated, "skipped": skipped}
