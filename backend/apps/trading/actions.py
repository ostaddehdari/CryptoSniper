"""Operator Paper close serialized with SL/TP on the same Trade row lock."""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.audit import record_audit
from apps.exchanges.adapters import get_adapter

from .exits_engine import _payout
from .models import Order, Position, Trade, TradeAction, TradeEvent, TradeProtection


def _supported(trade):
    return (
        trade.mode == "paper"
        and trade.account.environment == "paper"
        and trade.account.exchange.adapter_code == "simulator"
        and trade.market.market_type == "spot"
        and trade.side == "buy"
    )


def _entry_settled(trade):
    # Unfilled/unknown entry must be reconciled before closing: a late fill
    # could otherwise reopen a supposedly closed position.
    orders = list(trade.orders.all())
    return bool(orders) and all(
        o.state in (Order.State.FILLED, Order.State.CANCELLED) for o in orders
    )


@transaction.atomic
def request_close(owner, trade_id, *, request_key, revision, confirmed):
    trade = (
        Trade.objects.select_for_update(of=("self",))
        .select_related("account__exchange", "market")
        .get(pk=trade_id, owner=owner)
    )
    if confirmed is not True:
        raise ValidationError("بستن مقدار باقی‌مانده نیاز به تأیید صریح دارد.")
    request_key = UUID(str(request_key))
    revision = int(revision)
    existing = TradeAction.objects.filter(trade=trade, request_key=request_key).first()
    if existing:
        if existing.revision != revision:
            raise ValidationError("کلید درخواست با نسخهٔ دیگری استفاده شده است.")
        return existing, False
    if not _supported(trade):
        raise ValidationError("فقط Paper Spot Long شبیه‌ساز مجاز است.")
    if trade.revision != revision:
        raise ValidationError("نسخه صفحه قدیمی است؛ صفحه را تازه کنید.")
    if trade.state != Trade.State.OPEN or not _entry_settled(trade):
        raise ValidationError("ابتدا نتیجه ورود نامعلوم یا ناقص را در مرکز عملیات تطبیق دهید.")
    if TradeProtection.objects.filter(trade=trade, coverage="cancelling").exists():
        raise ValidationError("لغو خروج هنوز قطعی نیست؛ ابتدا تطبیق کنید.")
    pending = TradeAction.objects.filter(trade=trade, state__in=["pending", "waiting_feed"]).first()
    if pending:
        return pending, False
    action = TradeAction.objects.create(trade=trade, request_key=request_key, revision=revision)
    TradeEvent.objects.create(
        trade=trade, event_type="MANUAL_CLOSE_REQUESTED", payload={"action_id": action.pk}
    )
    record_audit(
        "paper_trade.close_requested",
        user=owner,
        metadata={"trade_id": trade.pk, "action_id": action.pk},
    )
    # Beat recovers the durable row if the broker is unavailable at request time.
    return action, True


def execute_close(action_id):
    info = TradeAction.objects.select_related("trade__market", "trade__protection").get(
        pk=action_id
    )
    if info.state in ("done", "rejected"):
        return {"state": info.state, **info.result}
    quote = None
    if not info.trade.protection.paper_scenario:
        try:
            quote = get_adapter("simulator", credentials={}, environment="paper").fetch_ticker(
                info.trade.market.symbol
            )
        except Exception:
            # Never turn a missing quote into a fictional fill or failed order.
            quote = None
    return _apply_close(action_id, quote)


@transaction.atomic
def _apply_close(action_id, quote):
    trade_id = TradeAction.objects.values_list("trade_id", flat=True).get(pk=action_id)
    trade = (
        Trade.objects.select_for_update(of=("self",))
        .select_related("account__exchange", "market")
        .get(pk=trade_id)
    )
    action = TradeAction.objects.select_for_update().get(pk=action_id)
    if action.state in ("done", "rejected"):
        return {"state": action.state, **action.result}
    action.attempts += 1
    rule = TradeProtection.objects.select_for_update().get(trade=trade)
    position = Position.objects.select_for_update().get(trade=trade)
    if trade.state == Trade.State.CLOSED and position.quantity == 0:
        action.state, action.code = "done", "already_closed"
        action.result = {"remaining": "0"}
    elif (
        not _supported(trade)
        or trade.state != Trade.State.OPEN
        or not _entry_settled(trade)
        or rule.coverage == TradeProtection.Coverage.CANCELLING
    ):
        action.state, action.code = "rejected", "reconciliation_required"
    else:
        price = rule.last_price if rule.paper_scenario else (quote.price if quote else None)
        observed = (
            rule.last_tick_at if rule.paper_scenario else (quote.observed_at if quote else None)
        )
        valid = (
            isinstance(price, Decimal)
            and price.is_finite()
            and price > 0
            and observed is not None
            and -5 <= (timezone.now() - observed).total_seconds() <= 55
        )
        if not valid:
            action.state, action.code = "waiting_feed", "fresh_quote_required"
            action.next_attempt_at = timezone.now() + timedelta(seconds=15)
        elif position.quantity <= 0 or trade.market.taker_fee is None:
            action.state, action.code = "rejected", "position_or_fee_unknown"
        else:
            fill = _payout(
                trade=trade,
                position=position,
                protection=rule,
                price=price,
                quantity=position.quantity,
                reason="manual_close",
                key=f"action-{action.pk}",
            )
            rule.version += 1
            rule.save()
            action.state, action.code = "done", "closed"
            action.result = {
                "fill_id": fill.pk,
                "quantity": str(fill.quantity),
                "price": str(fill.price),
                "remaining": "0",
            }
            record_audit(
                "paper_trade.close_completed",
                user=trade.owner,
                metadata={"trade_id": trade.pk, "action_id": action.pk, "fill_id": fill.pk},
            )
    action.save()
    TradeEvent.objects.create(
        trade=trade,
        event_type="MANUAL_CLOSE_RESULT",
        payload={"action_id": action.pk, "state": action.state, "code": action.code},
    )
    return {"state": action.state, "code": action.code, **action.result}
