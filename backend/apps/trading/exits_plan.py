"""Independent, immutable target allocations based on approved TradePlan snapshot.

Stage09-10: Only Paper Spot Long is allowed to perform an exit.
"""
from decimal import Decimal, ROUND_DOWN

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Trade, TradeEvent, TradeProtection, TradeTarget


def _decimal(raw):
    try:
        result = Decimal(str(raw))
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValidationError("مقدار عددی طرح خروج نامعتبر است.") from exc
    if not result.is_finite() or result <= 0:
        raise ValidationError("اعداد طرح خروج باید مثبت و محدود باشند.")
    return result


@transaction.atomic
def ensure_exits(trade_id):
    trade = Trade.objects.select_for_update().select_related(
        "account", "account__exchange", "market"
    ).get(pk=trade_id)
    if trade.mode != "paper" or trade.account.environment != "paper":
        raise ValidationError("ایجاد خروج فقط برای حساب Paper مجاز است.")
    if trade.account.exchange.adapter_code != "simulator" or trade.side != "buy":
        raise ValidationError("خروج Paper فقط برای Spot Long شبیه‌ساز مجاز است.")
    if trade.market.market_type != "spot":
        raise ValidationError("Margin/Futures در این مرحله پشتیبانی نمی‌شوند.")
    existing = TradeProtection.objects.filter(trade=trade).first()
    if existing:
        return existing, False
    source = trade.snapshot
    raw_targets = source.get("targets")
    if not isinstance(raw_targets, list) or not 1 <= len(raw_targets) <= 3:
        raise ValidationError("Snapshot اهداف معتبر ندارد.")
    shares = [_decimal(t["share_percent"]) for t in raw_targets]
    if sum(shares, Decimal("0")) != Decimal("100"):
        raise ValidationError("جمع سهم اهداف باید دقیقاً ۱۰۰٪ باشد.")
    stop = _decimal(source.get("stop_loss"))
    entry = _decimal(source.get("entry_price"))
    prices = [_decimal(t["price"]) for t in raw_targets]
    if stop >= entry or any(price <= entry for price in prices) or prices != sorted(set(prices)):
        raise ValidationError("ترتیب اهداف یا Stop در طرح نامعتبر است.")
    step = trade.market.amount_step
    if step is None or step <= 0:
        raise ValidationError("Lot step بازار برای تخصیص اهداف لازم است.")
    # target allocations are based on order quantity; pending/unfilled volume is
    # never allowed to exit before the entry is actually filled.
    allocated = Decimal("0")
    targets = []
    for position, (price, share) in enumerate(zip(prices, shares, strict=True), 1):
        if position == len(prices):
            quantity = trade.quantity - allocated
        else:
            quantity = ((trade.quantity * share / Decimal("100")) / step).to_integral_value(
                rounding=ROUND_DOWN
            ) * step
        if quantity < 0:
            raise ValidationError("تخصیص اهداف منفی شد.")
        allocated += quantity
        targets.append(TradeTarget(
            trade=trade, position=position, price=price,
            share_percent=share, allocated_quantity=quantity,
        ))
    if allocated != trade.quantity:
        raise ValidationError("جمع حجم اهداف با معامله هم‌خوان نیست.")
    TradeTarget.objects.bulk_create(targets)
    percentage = bool(source.get("percentage_trailing"))
    distance = _decimal(source.get("trailing_distance_percent", "1"))
    if distance >= 100:
        raise ValidationError("فاصله trailing باید کمتر از ۱۰۰٪ باشد.")
    protection = TradeProtection.objects.create(
        trade=trade, initial_stop=stop, effective_stop=stop,
        coverage=TradeProtection.Coverage.PENDING,
        step_enabled=bool(source.get("trailing_sl")),
        percentage_enabled=percentage,
        distance_percent=distance,
        trigger_price=prices[0],
    )
    TradeEvent.objects.create(
        trade=trade, event_type="EXIT_PLAN_CREATED",
        payload={"targets":len(targets), "percentage_trailing":percentage,
                 "mode":"paper_backend", "native_stop":False},
    )
    return protection, True
