"""Transactional PAPER price/exit engine. No real exchange order is submitted.

Single trade-level PostgreSQL row lock serializes SL, TP and trailing decisions.
"""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .exits_plan import ensure_exits
from .models import (
    CapitalReservation,
    PaperExitFill,
    PaperPriceEvent,
    Position,
    Trade,
    TradeEvent,
    TradeProtection,
    TradeTarget,
)
from .trailing_math import monotonic_stop, percentage_stop


def _value(value):
    try:
        price = Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValidationError("قیمت Paper معتبر نیست.") from exc
    if not price.is_finite() or price <= 0:
        raise ValidationError("قیمت Paper باید مثبت و محدود باشد.")
    return price


def _payout(*, trade, position, protection, price, quantity, reason, key, target=None):
    """Caller owns the Trade lock; total output can never exceed position."""
    if trade.mode != "paper" or trade.account.environment != "paper":
        raise ValidationError("خروج فقط در Paper Simulator مجاز است.")
    if quantity <= 0 or quantity > position.quantity:
        raise ValidationError("حجم خروج از Position موجود بیشتر است.")
    fill_key = str(key)[:100]
    fee_rate = trade.market.taker_fee
    if fee_rate is None:
        raise ValidationError("کارمزد خروج در بازار مشخص نیست.")
    fee = quantity * price * fee_rate
    fill = PaperExitFill.objects.create(
        trade=trade,
        target=target,
        tick_key=fill_key,
        reason=reason,
        quantity=quantity,
        price=price,
        fee=fee,
        occurred_at=timezone.now(),
    )
    position.quantity -= quantity
    position.total_fees += fee
    position.save(update_fields=("quantity", "total_fees", "updated_at"))
    if target:
        target.filled_quantity += quantity
        target.state = (
            TradeTarget.State.FILLED
            if target.filled_quantity == target.allocated_quantity
            else TradeTarget.State.PARTIAL
        )
        target.save(update_fields=("filled_quantity", "state"))
    TradeEvent.objects.create(
        trade=trade,
        event_type="PAPER_EXIT_FILL",
        payload={
            "id": fill.pk,
            "reason": reason,
            "price": str(price),
            "quantity": str(quantity),
            "remaining": str(position.quantity),
        },
    )
    if position.quantity == 0:
        trade.state = Trade.State.CLOSED
        trade.revision += 1
        trade.save(update_fields=("state", "revision", "updated_at"))
        protection.coverage = TradeProtection.Coverage.CLOSED
        CapitalReservation.objects.filter(trade=trade).update(active=False)
        TradeTarget.objects.filter(
            trade=trade, state__in=[TradeTarget.State.WAITING, TradeTarget.State.PARTIAL]
        ).update(state=TradeTarget.State.CANCELLED)
        from apps.alerts.models import PriceAlert

        PriceAlert.objects.filter(trade=trade, enabled=True).update(
            enabled=False, status="trade_closed"
        )
        TradeEvent.objects.create(
            trade=trade,
            event_type="PAPER_CLOSED",
            payload={"reason": reason, "final_exit": str(price)},
        )
        if trade.market.market_type == "margin":
            from .margin import repay_margin_loan

            repay_margin_loan(trade.pk)
    return fill


@transaction.atomic
def process_paper_price(
    trade_id, *, price, observed_at=None, event_key=None, source="simulator", max_fill_quantity=None
):
    """Process a unique fresh price in a DB transaction; always PAPER ONLY.

    Price may be injected only via authenticated Paper scenario or public simulator.
    Binance price events and live orders are prohibited here.
    """
    now = timezone.now()
    observed_at = observed_at or now
    if timezone.is_naive(observed_at):
        raise ValidationError("زمان قیمت باید با timezone ارسال شود.")
    if observed_at < now - timedelta(seconds=90) or observed_at > now + timedelta(seconds=5):
        raise ValidationError("قیمت قدیمی یا متعلق به آینده پذیرفته نمی‌شود.")
    if source not in {"simulator", "paper_scenario"}:
        raise ValidationError("منبع این Tick برای اجرای Paper مجاز نیست.")
    price = _value(price)
    trade = (
        Trade.objects.select_for_update(of=("self",))
        .select_related("account", "account__exchange", "market")
        .get(pk=trade_id)
    )
    if (
        trade.mode != "paper"
        or trade.account.environment != "paper"
        or trade.account.exchange.adapter_code != "simulator"
        or trade.market.market_type not in {"spot", "margin"}
        or trade.side not in {"buy", "sell"}
        or (trade.market.market_type == "spot" and trade.side != "buy")
    ):
        raise ValidationError("فقط شبیه‌ساز Paper Spot Long یا Margin Long/Short مجاز است.")
    if trade.state not in {Trade.State.OPEN, Trade.State.PARTIAL}:
        return {
            "status": "inactive",
            "remaining": "0" if trade.state == Trade.State.CLOSED else None,
        }
    protection = TradeProtection.objects.select_for_update().filter(trade=trade).first()
    if protection is None:
        protection, _ = ensure_exits(trade.pk)
    if protection.paper_scenario and source == "simulator":
        return {"status": "scenario_mode"}
    if source == "paper_scenario" and not protection.paper_scenario:
        raise ValidationError("ابتدا حالت سناریوی Paper را انتخاب کنید.")
    key = str(event_key or uuid4().hex)
    if len(key) > 100 or not key:
        raise ValidationError("شناسه رویداد بازار نامعتبر است.")
    if PaperPriceEvent.objects.filter(trade=trade, event_key=key).exists():
        return {"status": "duplicate"}
    if protection.last_tick_at and observed_at <= protection.last_tick_at:
        return {"status": "old_tick"}
    if protection.coverage == TradeProtection.Coverage.CANCELLING:
        return {"status": "cancel_reconciliation_pending"}
    position = Position.objects.select_for_update().filter(trade=trade).first()
    if not position or position.quantity <= 0:
        return {"status": "no_position"}
    tick = PaperPriceEvent.objects.create(
        trade=trade, event_key=key, price=price, observed_at=observed_at, source=source
    )
    protection.last_price = price
    protection.last_tick_at = observed_at
    protection.coverage = TradeProtection.Coverage.MONITORED
    protection.version += 1
    fills = []
    # Percentage ON from start makes all targets activation/display markers only.
    # Trailing activation preempts staged sell, and never weakens the stop.
    long_side = trade.side == "buy"
    if protection.percentage_enabled:
        reached_trigger = (
            price >= protection.trigger_price if long_side else price <= protection.trigger_price
        )
        if not protection.percentage_active and reached_trigger:
            protection.percentage_active = True
            if long_side:
                protection.high_water = price
            else:
                protection.low_water = price
            TradeEvent.objects.create(
                trade=trade,
                event_type="PERCENTAGE_ACTIVATED",
                payload={"price": str(price), "distance": str(protection.distance_percent)},
            )
        if protection.percentage_active:
            if long_side:
                protection.high_water = max(protection.high_water or price, price)
                derived = percentage_stop(
                    side="long", high=protection.high_water, distance=protection.distance_percent
                )
                protection.effective_stop = monotonic_stop(
                    "long", protection.effective_stop, derived
                )
            else:
                protection.low_water = min(protection.low_water or price, price)
                derived = percentage_stop(
                    side="short", low=protection.low_water, distance=protection.distance_percent
                )
                protection.effective_stop = monotonic_stop(
                    "short", protection.effective_stop, derived
                )
    stop_hit = (
        price <= protection.effective_stop if long_side else price >= protection.effective_stop
    )
    if stop_hit:
        fill = _payout(
            trade=trade,
            position=position,
            protection=protection,
            price=price,
            quantity=position.quantity,
            reason="stop",
            key=key,
        )
        fills.append(fill.pk)
    elif not protection.percentage_enabled:
        # Low watermark is used only by Percentage Margin Short; staged targets use direction.
        cap = _value(max_fill_quantity) if max_fill_quantity is not None else None
        for target in (
            TradeTarget.objects.select_for_update().filter(trade=trade).order_by("position")
        ):
            target_hit = price >= target.price if long_side else price <= target.price
            if not target_hit or target.state in {
                TradeTarget.State.CANCELLED,
                TradeTarget.State.FILLED,
            }:
                continue
            due = target.allocated_quantity - target.filled_quantity
            size = min(due, position.quantity)
            if cap is not None:
                size = min(size, cap)
            if size <= 0:
                continue
            fill = _payout(
                trade=trade,
                position=position,
                protection=protection,
                price=price,
                quantity=size,
                reason=f"tp{target.position}",
                key=key,
                target=target,
            )
            fills.append(fill.pk)
            if (
                protection.step_enabled
                and target.position == 1
                and target.state == TradeTarget.State.FILLED
            ):
                stop = trade.entry_price
                improves_stop = (
                    stop > protection.effective_stop
                    if long_side
                    else stop < protection.effective_stop
                )
                if improves_stop:
                    protection.effective_stop = stop
                    TradeEvent.objects.create(
                        trade=trade,
                        event_type="TRAILING_SL_BREAKEVEN",
                        payload={"trigger": "tp1", "stop": str(stop), "one_shot": True},
                    )
            if trade.state == Trade.State.CLOSED:
                break
            if cap is not None:
                break
    protection.save()
    return {
        "status": "closed" if trade.state == Trade.State.CLOSED else "monitored",
        "fill_ids": fills,
        "tick_id": tick.pk,
        "stop": str(protection.effective_stop),
        "remaining": str(position.quantity),
        "percentage_active": protection.percentage_active,
    }
