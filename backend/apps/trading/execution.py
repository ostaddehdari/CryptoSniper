"""Durable Paper-only executor; never calls any Binance order endpoint."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.exchanges.adapters import AdapterError, get_adapter

from .exits_plan import ensure_exits
from .models import (
    CapitalReservation,
    ExecutionOutbox,
    Order,
    OrderFill,
    Position,
    Trade,
    TradeEvent,
)


@transaction.atomic
def record_fill(order_id, *, exchange_fill_id, quantity, price, fee=Decimal("0")):
    """Idempotent fill ingestion with position calculated ONLY from unique fills."""
    order = Order.objects.select_for_update().select_related("trade").get(pk=order_id)
    trade = Trade.objects.select_for_update().get(pk=order.trade_id)
    quantity = Decimal(str(quantity))
    price = Decimal(str(price))
    fee = Decimal(str(fee))
    if not quantity.is_finite() or quantity <= 0 or not price.is_finite() or price <= 0:
        raise ValidationError("Fill مقدار و قیمت معتبر لازم دارد.")
    if not fee.is_finite() or fee < 0:
        raise ValidationError("کارمزد Fill نامعتبر است.")
    existing = OrderFill.objects.filter(
        account=order.account, exchange_fill_id=exchange_fill_id
    ).first()
    if existing:
        if (existing.order_id, existing.quantity, existing.price, existing.fee) != (
            order.pk,
            quantity,
            price,
            fee,
        ):
            raise ValidationError("شناسه Fill با اطلاعات متفاوت قبلاً ثبت شده است.")
        return existing, False
    if order.state in {Order.State.CANCELLED, Order.State.FAILED}:
        raise ValidationError("برای سفارش لغوشده یا شکست‌خورده Fill جدید نمی‌پذیریم.")
    if order.filled_quantity + quantity > order.quantity:
        raise ValidationError("حجم Fill از حجم باقی‌مانده سفارش بیشتر است.")
    fill = OrderFill.objects.create(
        order=order,
        account=order.account,
        exchange_fill_id=exchange_fill_id,
        quantity=quantity,
        price=price,
        fee=fee,
        occurred_at=timezone.now(),
    )
    order.filled_quantity += quantity
    trade.filled_quantity += quantity
    complete = order.filled_quantity == order.quantity
    order.state = Order.State.FILLED if complete else Order.State.PARTIAL
    trade.state = Trade.State.OPEN if complete else Trade.State.PARTIAL
    order.save(update_fields=("filled_quantity", "state", "updated_at"))
    trade.revision += 1
    trade.save(update_fields=("filled_quantity", "state", "revision", "updated_at"))
    pos, _ = Position.objects.select_for_update().get_or_create(
        trade=trade, defaults={"account": order.account}
    )
    old_qty = pos.quantity
    pos.quantity += quantity
    pos.average_entry = ((pos.average_entry * old_qty) + (price * quantity)) / pos.quantity
    pos.total_fees += fee
    pos.save()
    CapitalReservation.objects.filter(trade=trade).update(spent=True)
    TradeEvent.objects.create(
        trade=trade,
        event_type="FILL",
        payload={
            "fill_id": fill.pk,
            "quantity": str(quantity),
            "price": str(price),
            "total_filled": str(trade.filled_quantity),
        },
    )
    if complete:
        TradeEvent.objects.create(
            trade=trade, event_type="ENTRY_FILLED", payload={"order_id": order.pk}
        )
    ensure_exits(trade.pk)
    return fill, True


@transaction.atomic
def claim_outbox(outbox_id):
    """Never resubmit a potentially sent order; uncertain requires reconciliation."""
    box = ExecutionOutbox.objects.select_for_update().select_related("order").get(pk=outbox_id)
    if box.state != ExecutionOutbox.State.PENDING:
        return None
    order = Order.objects.select_for_update().get(pk=box.order_id)
    trade = Trade.objects.select_for_update().get(pk=order.trade_id)
    if order.state != Order.State.QUEUED or trade.state != Trade.State.QUEUED:
        raise ValidationError("وضعیت سفارش قابل ارسال نیست.")
    box.state = ExecutionOutbox.State.INFLIGHT
    box.attempts += 1
    box.save(update_fields=("state", "attempts", "updated_at"))
    order.state = Order.State.SUBMITTING
    order.sent_at = timezone.now()
    order.save(update_fields=("state", "sent_at", "updated_at"))
    trade.state = Trade.State.SUBMITTING
    trade.save(update_fields=("state", "updated_at"))
    TradeEvent.objects.create(
        trade=trade, event_type="SUBMIT_INTENT", payload={"client_order_id": order.client_order_id}
    )
    return order.pk


@transaction.atomic
def mark_uncertain(outbox_id, code="unknown_outcome"):
    box = ExecutionOutbox.objects.select_for_update().get(pk=outbox_id)
    if box.state != ExecutionOutbox.State.INFLIGHT:
        return
    order = Order.objects.select_for_update().get(pk=box.order_id)
    trade = Trade.objects.select_for_update().get(pk=order.trade_id)
    if order.state in {Order.State.FILLED, Order.State.PARTIAL}:
        box.state = ExecutionOutbox.State.DONE
        box.save(update_fields=("state", "updated_at"))
        return
    box.state = ExecutionOutbox.State.UNCERTAIN
    box.last_error_code = code[:50]
    box.save(update_fields=("state", "last_error_code", "updated_at"))
    order.state = Order.State.UNCERTAIN
    order.save(update_fields=("state", "updated_at"))
    trade.state = Trade.State.UNCERTAIN
    trade.save(update_fields=("state", "updated_at"))
    TradeEvent.objects.create(
        trade=trade, event_type="OUTCOME_UNKNOWN", payload={"reason_code": code[:50]}
    )


def dispatch_paper(outbox_id):
    """External simulator invocation outside DB transaction, after durable intent."""
    order_id = claim_outbox(outbox_id)
    if order_id is None:
        return {"status": "already_claimed"}
    order = Order.objects.select_related("trade", "account", "trade__market").get(pk=order_id)
    if (
        order.account.environment != "paper"
        or order.account.exchange.adapter_code != "simulator"
        or order.trade.market.market_type != "spot"
    ):
        mark_uncertain(outbox_id, "unsafe_provider")
        return {"status": "uncertain"}
    try:
        adapter = get_adapter("simulator", credentials={}, environment="paper")
        receipt = adapter.place_order(
            client_order_id=order.client_order_id,
            symbol=order.trade.market.symbol,
            side="buy",
            order_type="market",
            amount=order.quantity,
            price=order.price,
        )
        with transaction.atomic():
            locked = Order.objects.select_for_update().get(pk=order.pk)
            locked.external_order_id = receipt.order_id
            locked.save(update_fields=("external_order_id", "updated_at"))
        if receipt.filled_amount > 0:
            record_fill(
                order.pk,
                exchange_fill_id=f"paper:{order.client_order_id}:1",
                quantity=receipt.filled_amount,
                price=receipt.average_price or order.price,
                fee=receipt.filled_amount
                * (receipt.average_price or order.price)
                * (order.trade.market.taker_fee or Decimal("0")),
            )
        with transaction.atomic():
            box = ExecutionOutbox.objects.select_for_update().get(pk=outbox_id)
            box.state = ExecutionOutbox.State.DONE
            box.save(update_fields=("state", "updated_at"))
        return {"status": "filled", "order_id": order.pk}
    except (AdapterError, ValidationError, ValueError, ArithmeticError):
        mark_uncertain(outbox_id, "paper_adapter_error")
        return {"status": "uncertain"}


def expire_inflight(seconds=30):
    cutoff = timezone.now() - timedelta(seconds=seconds)
    ids = list(
        ExecutionOutbox.objects.filter(
            state=ExecutionOutbox.State.INFLIGHT, updated_at__lt=cutoff
        ).values_list("pk", flat=True)[:30]
    )
    for outbox_id in ids:
        mark_uncertain(outbox_id, "worker_restart_or_timeout")
    return len(ids)


@transaction.atomic
def cancel_unsubmitted(owner, trade_id):
    trade = Trade.objects.select_for_update().get(pk=trade_id, owner=owner)
    if trade.state != Trade.State.QUEUED:
        raise ValidationError("لغو فقط پیش از ارسال سفارش مجاز است.")
    order = Order.objects.select_for_update().get(trade=trade)
    box = ExecutionOutbox.objects.select_for_update().get(order=order)
    if box.state != ExecutionOutbox.State.PENDING:
        raise ValidationError("سفارش قبلاً برای اجرا برداشته شده است.")
    trade.state = Trade.State.CANCELLED
    order.state = Order.State.CANCELLED
    box.state = ExecutionOutbox.State.DONE
    trade.save(update_fields=("state", "updated_at"))
    order.save(update_fields=("state", "updated_at"))
    box.save(update_fields=("state", "updated_at"))
    CapitalReservation.objects.filter(trade=trade).update(active=False)
    TradeEvent.objects.create(trade=trade, event_type="CANCEL_BEFORE_SUBMIT")
    return trade
