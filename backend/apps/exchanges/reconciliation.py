"""Provider evidence only: cumulative receipts never decrease and unknown writes never retry."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .adapters import AdapterError, InvalidProviderResponse, OrderStatus, get_adapter
from .live_orders import _validate_receipt
from .models import LiveSpotOrder
from .security import get_account_credentials

TERMINAL = {"filled", "cancelled", "failed"}
MAPPED = {
    OrderStatus.OPEN: "open",
    OrderStatus.PARTIAL: "partial",
    OrderStatus.FILLED: "filled",
    OrderStatus.CANCELLED: "cancelled",
}


def account_adapter(account):
    if account.status not in {"connected", "restricted"} or not account.permissions.get("can_read"):
        raise ValidationError("حساب خواندنی و متصل لازم است.")
    return get_adapter(
        account.exchange.adapter_code,
        credentials=get_account_credentials(account),
        environment=account.environment,
    )


@transaction.atomic
def apply_receipt(order_id, receipt):
    order = LiveSpotOrder.objects.select_for_update().select_related("market").get(pk=order_id)
    _validate_receipt(order, receipt)
    if order.external_order_id and str(receipt.order_id) != order.external_order_id:
        raise InvalidProviderResponse("provider_order_id_mismatch")
    if receipt.filled_amount < order.filled_amount:
        raise InvalidProviderResponse("provider_fill_regression")
    if order.state in {"filled", "cancelled"} and MAPPED[receipt.status] != order.state:
        raise InvalidProviderResponse("provider_terminal_regression")
    order.external_order_id = str(receipt.order_id)
    order.filled_amount = receipt.filled_amount
    order.average_price = receipt.average_price
    order.state = MAPPED[receipt.status]
    order.error_code = ""
    order.save()
    return order


def reconcile_order(order_id, *, adapter=None, external_id=None, cancel=False):
    order = LiveSpotOrder.objects.select_related("account__exchange", "market").get(pk=order_id)
    if order.state in TERMINAL and not external_id:
        return order.state
    adapter = adapter or account_adapter(order.account)
    order_id_at_provider = order.external_order_id or external_id
    try:
        if order_id_at_provider:
            receipt = adapter.fetch_order(order_id_at_provider)
            _validate_receipt(order, receipt)
            if cancel and receipt.status not in {OrderStatus.FILLED, OrderStatus.CANCELLED}:
                # Verify identity BEFORE the side effect; then require terminal evidence.
                adapter.cancel_order(order_id_at_provider)
                receipt = adapter.fetch_order(order_id_at_provider)
        else:
            receipts = [
                r
                for r in adapter.fetch_open_orders()
                if r.client_order_id and r.client_order_id == order.client_order_id
            ]
            if len(receipts) != 1:
                if order.state == "submitting" and order.updated_at < timezone.now() - timedelta(
                    seconds=90
                ):
                    LiveSpotOrder.objects.filter(pk=order.pk, state="submitting").update(
                        state="uncertain", error_code="worker_lost_after_submission"
                    )
                return "unresolved"
            receipt = receipts[0]
        apply_receipt(order.pk, receipt)
        return MAPPED[receipt.status]
    except (AdapterError, ValidationError, ValueError, ArithmeticError, OSError, TimeoutError):
        if cancel:
            LiveSpotOrder.objects.filter(pk=order.pk).exclude(state__in=TERMINAL).update(
                state="uncertain", error_code="cancel_unconfirmed"
            )
        return "unresolved"


def reconcile_account_orders(account):
    adapter = account_adapter(account)
    ids = (
        LiveSpotOrder.objects.filter(account=account)
        .exclude(state__in=TERMINAL)
        .order_by("updated_at")
        .values_list("pk", flat=True)[:50]
    )
    return {str(pk): reconcile_order(pk, adapter=adapter) for pk in ids}
