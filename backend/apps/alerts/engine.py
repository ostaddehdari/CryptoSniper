"""Crossing + hysteresis, monotonic timestamp, one transaction per alert event."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import AlertEvent, Notification, NotificationPreference, PriceAlert

PROXIMITY = {"near_sl", "near_activation", "near_stop"}
TRADE_ONLY = PROXIMITY | {"profit", "entry_change"}


def condition(alert, metric):
    below = alert.kind in PROXIMITY or (
        alert.kind not in {"rise", "fall"} and alert.direction == "below"
    )
    return metric <= alert.threshold if below else metric >= alert.threshold


def rearm_condition(alert, metric):
    # Price hysteresis is a percentage of threshold; other metrics use percentage points.
    margin = (
        abs(alert.threshold) * alert.hysteresis / 100 if alert.kind == "price" else alert.hysteresis
    )
    below = alert.kind in PROXIMITY or (
        alert.kind not in {"rise", "fall"} and alert.direction == "below"
    )
    return metric > alert.threshold + margin if below else metric < alert.threshold - margin


def metric_for(alert, price):
    if alert.kind == "price":
        return price, {"unit": "quote_price"}
    if alert.kind in {"rise", "fall"}:
        change = (price - alert.reference_price) / alert.reference_price * 100
        return (change if alert.kind == "rise" else -change), {
            "unit": "percent",
            "reference": str(alert.reference_price),
            "reference_at": alert.reference_at.isoformat(),
        }
    from .trade_metrics import trade_metric

    return trade_metric(alert, price)


@transaction.atomic
def evaluate(alert_id, *, price, observed_at, source):
    now = timezone.now()
    price = Decimal(str(price))
    if not price.is_finite() or price <= 0:
        raise ValidationError("قیمت هشدار باید مثبت و محدود باشد.")
    if (
        timezone.is_naive(observed_at)
        or observed_at < now - timedelta(seconds=40)
        or observed_at > now + timedelta(seconds=5)
    ):
        return "stale"
    # Always trade -> alert lock, same as exit close which disables linked alerts.
    trade_id = PriceAlert.objects.values_list("trade_id", flat=True).get(pk=alert_id)
    if trade_id:
        from apps.trading.models import Trade

        Trade.objects.select_for_update().get(pk=trade_id)
    alert = (
        PriceAlert.objects.select_for_update(of=("self",))
        .select_related("trade", "market__exchange")
        .get(pk=alert_id)
    )
    if not alert.enabled:
        return "disabled"
    if alert.trade and alert.trade.state not in {"open", "partially_filled"}:
        alert.enabled, alert.status = False, "trade_closed"
        alert.save(update_fields=("enabled", "status", "updated_at"))
        return "trade_closed"
    allowed_source = (
        "paper_scenario"
        if alert.trade and alert.trade.protection.paper_scenario
        else alert.market.exchange.adapter_code
    )
    if source != allowed_source:
        return "wrong_source"
    from apps.marketdata.search import market_is_readable

    if not market_is_readable(alert.owner, alert.market):
        return "connection_unavailable"
    if not alert.market.active:
        return "market_inactive"
    if alert.last_observed_at and observed_at <= alert.last_observed_at:
        return "duplicate"
    metric, basis = metric_for(alert, price)
    alert.last_observed_at = observed_at
    if metric is None:
        alert.status = "waiting_for_basis"
        alert.save(update_fields=("last_observed_at", "status", "updated_at"))
        return "waiting_for_basis"
    fire = alert.armed and condition(alert, metric)
    if alert.last_fired_at and now < alert.last_fired_at + timedelta(
        seconds=alert.cooldown_seconds
    ):
        fire = False
    if not alert.armed and rearm_condition(alert, metric):
        alert.armed = True
    alert.last_metric = metric
    alert.status = "watching"
    if fire:
        alert.fire_count += 1
        alert.last_fired_at = now
        alert.armed = False
        if not alert.repeat:
            alert.enabled, alert.status = False, "triggered"
        event = AlertEvent.objects.create(
            alert=alert,
            sequence=alert.fire_count,
            observed_at=observed_at,
            price=price,
            metric=metric,
            basis=basis,
        )
        preferences, _ = NotificationPreference.objects.get_or_create(owner=alert.owner)
        Notification.objects.create(
            owner=alert.owner,
            event=event,
            title=alert.title,
            body=(
                f"{alert.market.symbol} · قیمت {price} · {alert.get_kind_display()} ({metric:.4f})"
            ),
            severity="warning" if alert.kind in PROXIMITY else "info",
            in_app=preferences.in_app,
            browser=preferences.browser,
        )
    alert.save()
    return "fired" if fire else "observed"
