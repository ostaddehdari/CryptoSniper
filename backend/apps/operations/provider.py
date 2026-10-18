"""Persistent simulator provider. Real adapters keep their explicit read-only boundary."""

import hashlib
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import PaperProviderOrder


@transaction.atomic
def submit(order):
    from apps.trading.boundary import require_paper_simulator
    from apps.trading.models import Order, Trade

    Trade.objects.select_for_update(of=("self",)).get(pk=order.trade_id)
    order = (
        Order.objects.select_for_update(of=("self",))
        .select_related("account__exchange", "trade__market")
        .get(pk=order.pk)
    )
    existing = lookup(order)
    if existing:
        return existing
    if order.state not in {"submitting", "uncertain"}:
        raise ValidationError("سفارش برای ارسال مجاز نیست.")
    account = require_paper_simulator(order)
    if order.trade.market.market_type not in {"spot", "margin"}:
        raise ValidationError("فقط بازار Spot یا Margin نسخه نخست مجاز است.")
    if order.trade.market.taker_fee is None:
        raise ValidationError("کارمزد بازار نامعلوم است.")
    key = hashlib.sha256(f"{account.pk}:{order.client_order_id}".encode()).hexdigest()[:40]
    receipt, _ = PaperProviderOrder.objects.get_or_create(
        account=account,
        client_order_id=order.client_order_id,
        defaults={
            "external_order_id": "paper-" + key,
            "symbol": order.trade.market.symbol,
            "quantity": order.quantity,
            "price": order.price,
            "fee": (order.quantity * order.price * order.trade.market.taker_fee).quantize(
                Decimal("0.0000000000000001")
            ),
        },
    )
    if (receipt.symbol, receipt.quantity, receipt.price) != (
        order.trade.market.symbol,
        order.quantity,
        order.price,
    ):
        raise ValidationError("تعارض شناسه سفارش در دفتر شبیه‌ساز.")
    return receipt


def lookup(order):
    return PaperProviderOrder.objects.filter(
        account=order.account, client_order_id=order.client_order_id
    ).first()
