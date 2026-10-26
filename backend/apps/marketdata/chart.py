"""Stage24 chart payload for live UI.

Candles are display-only public market data. Trade/signal overlays are private and owner scoped.
"""

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.security import session_api_required
from apps.operations.models import ExternalObservation, ExternalTradePolicy, ManagedSpotPosition
from apps.signals.models import Signal, SignalOutcome
from apps.trading.models import PaperExitFill, Trade

from .feeds import get_quote, refresh_quote
from .history import INTERVAL_MS, fetch_binance_history
from .models import HistoricalCandle
from .search import eligible_markets

CHART_INTERVALS = ("1m", "5m", "15m", "1h", "4h", "1d")
MAX_BARS = 300


def _number(value):
    return float(value) if value is not None else None


def _candle_payload(row):
    return {
        "time": int(row.open_time.timestamp()),
        "open": _number(row.open_price),
        "high": _number(row.high_price),
        "low": _number(row.low_price),
        "close": _number(row.close_price),
        "volume": _number(row.volume),
    }


def _touch(candles, price, side, *, after=None):
    if price is None:
        return None
    for row in candles:
        if after and row.open_time < after:
            continue
        if side == "short":
            hit = row.low_price <= price <= row.high_price
        else:
            hit = row.low_price <= price <= row.high_price
        if hit:
            return row.open_time
    return None


def _signal_overlay(user, signal_id, candles):
    signal = (
        Signal.objects.filter(owner=user, pk=signal_id)
        .select_related("market")
        .prefetch_related("targets")
        .first()
    )
    if not signal:
        return None
    levels = []
    if signal.entry_price is not None:
        levels.append({"kind": "entry", "label": "Entry", "price": _number(signal.entry_price)})
    for target in signal.targets.order_by("position"):
        levels.append(
            {
                "kind": f"tp{target.position}",
                "label": f"TP{target.position}",
                "price": _number(target.price),
            }
        )
    if signal.stop_loss is not None:
        levels.append({"kind": "sl", "label": "SL", "price": _number(signal.stop_loss)})

    markers = []
    outcome = SignalOutcome.objects.filter(signal=signal).first()
    start = signal.created_at
    entry_at = outcome.entry_hit_at if outcome else _touch(candles, signal.entry_price, signal.side)
    if entry_at:
        markers.append({"kind": "entry", "time": int(entry_at.timestamp()), "label": "Entry"})
        start = entry_at
    for target in signal.targets.order_by("position"):
        at = _touch(candles, target.price, signal.side, after=start)
        if at:
            markers.append(
                {
                    "kind": f"tp{target.position}",
                    "time": int(at.timestamp()),
                    "label": f"TP{target.position}",
                }
            )
    stop_at = (
        outcome.stop_hit_at
        if outcome
        else _touch(candles, signal.stop_loss, signal.side, after=start)
    )
    if stop_at:
        markers.append({"kind": "sl", "time": int(stop_at.timestamp()), "label": "SL"})
    if outcome and outcome.status == SignalOutcome.Status.EXPIRED and outcome.evaluated_until:
        markers.append(
            {
                "kind": "expired",
                "time": int(outcome.evaluated_until.timestamp()),
                "label": "Expired",
            }
        )
    return {
        "type": "signal",
        "id": signal.pk,
        "side": signal.side,
        "levels": levels,
        "markers": markers,
        "archived": signal.archived_at is not None,
    }


def _trade_overlay(user, trade_id):
    trade = (
        Trade.objects.filter(owner=user, pk=trade_id)
        .select_related("market", "protection")
        .prefetch_related("targets")
        .first()
    )
    if not trade:
        return None
    levels = [{"kind": "entry", "label": "Entry", "price": _number(trade.entry_price)}]
    for target in trade.targets.order_by("position"):
        levels.append(
            {
                "kind": f"tp{target.position}",
                "label": f"TP{target.position}",
                "price": _number(target.price),
            }
        )
    protection = getattr(trade, "protection", None)
    if protection:
        levels.append(
            {
                "kind": "sl",
                "label": "SL",
                "price": _number(protection.effective_stop),
            }
        )
    markers = [
        {
            "kind": "entry",
            "time": int(trade.created_at.timestamp()),
            "label": "Entry",
        }
    ]
    for fill in PaperExitFill.objects.filter(trade=trade).order_by("occurred_at"):
        kind = "sl" if fill.reason == "stop" else fill.reason
        markers.append(
            {
                "kind": kind,
                "time": int(fill.occurred_at.timestamp()),
                "label": str(fill.reason).upper(),
            }
        )
    return {
        "type": "internal_trade",
        "id": trade.pk,
        "side": trade.side,
        "levels": levels,
        "markers": markers,
        "state": trade.state,
        "archived": trade.archived_at is not None,
    }


def _external_overlay(user, observation_id):
    observation = (
        ExternalObservation.objects.filter(account__owner=user, pk=observation_id)
        .select_related("account__exchange")
        .first()
    )
    if not observation:
        return None
    policy = ExternalTradePolicy.objects.filter(observation=observation).first()
    payload = observation.payload if isinstance(observation.payload, dict) else {}
    levels = []
    markers = [
        {
            "kind": "external",
            "time": int(observation.observed_at.timestamp()),
            "label": "Exchange",
        }
    ]
    if policy:
        levels.append({"kind": "entry", "label": "Entry", "price": _number(policy.entry_price)})
        for pos, value in ((1, policy.tp1), (2, policy.tp2), (3, policy.tp3)):
            if value is not None:
                levels.append({"kind": f"tp{pos}", "label": f"TP{pos}", "price": _number(value)})
        levels.append({"kind": "sl", "label": "SL", "price": _number(policy.effective_stop)})
    elif payload.get("price"):
        levels.append({"kind": "entry", "label": "Price", "price": float(payload["price"])})
    return {
        "type": "external_trade",
        "id": observation.pk,
        "levels": levels,
        "markers": markers,
        "state": policy.state if policy else str(payload.get("status", "observed")).lower(),
        "archived": observation.archived_at is not None,
    }


def _managed_overlay(user, market_id, position_id=None, order_id=None):
    rows = ManagedSpotPosition.objects.filter(
        account__owner=user, market_id=market_id
    ).select_related("entry_order")
    position = (
        rows.filter(pk=position_id).first()
        if position_id
        else rows.filter(entry_order_id=order_id).first()
    )
    if not position:
        return None
    levels = [
        {"kind": "entry", "label": "Entry", "price": float(position.snapshot["entry_price"])},
        {"kind": "sl", "label": "SL", "price": float(position.effective_stop)},
    ]
    levels += [
        {"kind": f"tp{i + 1}", "label": f"TP{i + 1}", "price": float(t["price"])}
        for i, t in enumerate(position.snapshot["targets"])
    ]
    markers = []
    if position.entry_order and position.entry_order.filled_amount:
        markers.append(
            {
                "kind": "entry",
                "label": "Entry fill",
                "time": int(position.entry_order.updated_at.timestamp()),
            }
        )
    for attempt in position.exits.select_related("order").filter(order__filled_amount__gt=0):
        markers.append(
            {
                "kind": attempt.reason,
                "label": f"{attempt.reason} fill {attempt.order.filled_amount}",
                "time": int(attempt.order.updated_at.timestamp()),
            }
        )
    return {
        "type": "managed_spot",
        "id": position.pk,
        "levels": levels,
        "markers": markers,
        "state": position.state,
        "remaining": str(position.remaining),
        "markers_are_receipts": True,
        "time_basis": "receipt_observed_at",
    }


@session_api_required
@never_cache
@require_GET
def api_chart(request):
    try:
        market_id = int(request.GET.get("market", "0"))
        bars = min(max(int(request.GET.get("bars", "180")), 30), MAX_BARS)
    except ValueError:
        return JsonResponse({"error": "invalid_chart_parameters"}, status=400)
    interval = request.GET.get("interval", "5m")
    if interval not in CHART_INTERVALS:
        return JsonResponse({"error": "invalid_interval"}, status=400)
    market = (
        eligible_markets(request.user)
        .select_related("exchange")
        .filter(pk=market_id, active=True)
        .first()
    )
    if not market:
        return JsonResponse({"error": "market_not_found"}, status=404)

    now = timezone.now()
    step_ms = INTERVAL_MS[interval]
    start = now - timedelta(milliseconds=step_ms * (bars + 10))
    if getattr(settings, "MARKETDATA_REMOTE_HISTORY_ENABLED", True):
        try:
            fetch_binance_history(
                market.symbol,
                start,
                now + timedelta(minutes=1),
                interval=interval,
                max_pages=2,
            )
        except ValidationError:
            # Keep the UI useful when the public reference provider does not list a pair.
            pass

    candles = list(
        HistoricalCandle.objects.filter(
            provider="binance_public",
            symbol=market.symbol.upper(),
            interval=interval,
            open_time__gte=start,
        ).order_by("-open_time")[:bars]
    )
    candles.reverse()

    quote = get_quote(market)
    if not quote or quote.get("stale"):
        refresh_quote(market)
        quote = get_quote(market)

    candle_payloads = [_candle_payload(row) for row in candles]
    provider_label = "Binance public candles"
    if quote and quote.get("price") and not quote.get("stale"):
        live_price = float(quote["price"])
        live_point = {
            "time": int(now.timestamp()),
            "open": live_price,
            "high": live_price,
            "low": live_price,
            "close": live_price,
            "volume": 0.0,
            "live": True,
        }
        if candle_payloads and candle_payloads[-1]["time"] == live_point["time"]:
            candle_payloads[-1] = live_point
        else:
            candle_payloads.append(live_point)
        source = str(quote.get("source") or market.exchange.adapter_code)
        if market.exchange.adapter_code == "binance":
            provider_label = f"{source} live + Binance public candles"
        elif candles:
            provider_label = f"{source} live · Binance history reference"
        else:
            provider_label = f"{source} live · history unavailable"
    elif market.exchange.adapter_code != "binance":
        provider_label = f"{market.exchange.code} · live quote unavailable"

    if quote and quote.get("stale"):
        provider_label = (
            f"{quote.get('source', market.exchange.code)} quote stale · Binance history reference"
        )
    overlay = None
    if request.GET.get("position") or request.GET.get("live_order"):
        overlay = _managed_overlay(
            request.user, market.pk, request.GET.get("position"), request.GET.get("live_order")
        )
    elif request.GET.get("signal"):
        overlay = _signal_overlay(request.user, request.GET["signal"], candles)
    elif request.GET.get("trade"):
        overlay = _trade_overlay(request.user, request.GET["trade"])
    elif request.GET.get("external"):
        overlay = _external_overlay(request.user, request.GET["external"])

    return JsonResponse(
        {
            "market": {
                "id": market.pk,
                "symbol": market.symbol,
                "exchange": market.exchange.code,
            },
            "interval": interval,
            "provider": str(quote.get("source")) if quote else "binance_public_display_reference",
            "provider_label": provider_label,
            "candles": candle_payloads,
            "overlay": overlay,
            "as_of": now.isoformat(),
            "display_only": True,
            "candle_source": "binance_public_display_reference",
            "feed": {
                "stale": not quote or bool(quote.get("stale")),
                "observed_at": quote.get("observed_at") if quote else None,
                "age_seconds": quote.get("age_seconds") if quote else None,
                "source": quote.get("source") if quote else None,
            },
        }
    )
