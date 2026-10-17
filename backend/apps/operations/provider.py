"""Persistent simulator provider. Real adapters keep their explicit read-only boundary."""

import hashlib

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import PaperProviderOrder


@transaction.atomic
def submit(order):
    account = order.account
    if account.environment != "paper" or account.exchange.adapter_code != "simulator":
        raise ValidationError("فقط Simulator Paper مجاز است.")
    if order.trade.mode != "paper" or order.trade.market.market_type != "spot":
        raise ValidationError("فقط Paper Spot مجاز است.")
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
            "fee": order.quantity * order.price * order.trade.market.taker_fee,
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
