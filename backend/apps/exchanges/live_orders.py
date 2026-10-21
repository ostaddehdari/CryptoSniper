"""Durable, explicitly-confirmed direct Spot writes for verified no-withdrawal keys."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from .adapters import (
    AdapterError,
    AuthenticationError,
    OrderStatus,
    ProviderRejectedError,
    UnsupportedOperationError,
    get_adapter,
)
from .models import LiveSpotOrder, UserExchangeAccount
from .security import get_account_credentials


@transaction.atomic
def queue_live_spot_order(owner, account, cleaned):
    account = (
        UserExchangeAccount.objects.select_for_update()
        .select_related("exchange")
        .get(pk=account.pk, owner=owner)
    )
    request_key = cleaned["request_key"]
    existing = LiveSpotOrder.objects.filter(owner=owner, request_key=request_key).first()
    if existing:
        return existing, False
    if not settings.LIVE_TRADING_ENABLED:
        raise ValidationError("ارسال سفارش واقعی روی سرور خاموش است.")
    from apps.operations.models import AccountControl
    control, _ = AccountControl.objects.get_or_create(account=account)
    if control.paused:
        raise ValidationError("ورود جدید برای این حساب از مرکز عملیات متوقف شده است.")
    if (
        account.environment != "live"
        or account.status != "connected"
        or not account.trading_enabled
        or account.permissions.get("can_withdraw") is not False
        or account.permissions.get("can_trade_spot") is not True
    ):
        raise ValidationError("حساب Live ایمن و مجاز نیست.")
    market = cleaned["market"]
    if (
        market.exchange_id != account.exchange_id
        or market.market_type != "spot"
        or not market.active
    ):
        raise ValidationError("بازار Spot فعال متعلق به همین صرافی لازم است.")
    order = LiveSpotOrder.objects.create(
        owner=owner,
        account=account,
        market=market,
        request_key=request_key,
        client_order_id=f"cs-live-{owner.pk}-{request_key.hex[:24]}",
        side=cleaned["side"],
        order_type="limit",
        amount=cleaned["amount"],
        price=cleaned["price"],
    )
    return order, True


def execute_live_spot_order(order_id):
    with transaction.atomic():
        order = (
            LiveSpotOrder.objects.select_for_update()
            .select_related("account__exchange", "market")
            .get(pk=order_id)
        )
        if order.state != LiveSpotOrder.State.PENDING:
            return {"status": order.state}
        from apps.operations.models import AccountControl
        control, _ = AccountControl.objects.get_or_create(account=order.account)
        if (
            not settings.LIVE_TRADING_ENABLED
            or control.paused
            or order.account.status != "connected"
            or not order.account.trading_enabled
            or order.account.permissions.get("can_withdraw") is not False
        ):
            order.state, order.error_code = LiveSpotOrder.State.FAILED, "safety_gate_closed"
            order.save(update_fields=("state", "error_code", "updated_at"))
            return {"status": "failed"}
        order.state = LiveSpotOrder.State.SUBMITTING
        order.save(update_fields=("state", "updated_at"))

    try:
        adapter = get_adapter(
            order.account.exchange.adapter_code,
            credentials=get_account_credentials(order.account),
            environment=order.account.environment,
        )
        permission = adapter.validate_credentials()
        if not permission.safe_for_trading:
            raise ValidationError("مجوز Read+Spot بدون برداشت دیگر تأیید نمی‌شود.")
        receipt = adapter.place_order(
            client_order_id=order.client_order_id,
            symbol=order.market.symbol,
            side=order.side,
            order_type=order.order_type,
            amount=order.amount,
            price=order.price,
        )
    except (
        AuthenticationError,
        ProviderRejectedError,
        UnsupportedOperationError,
        ValidationError,
        ValueError,
    ) as error:
        with transaction.atomic():
            locked = LiveSpotOrder.objects.select_for_update().get(pk=order_id)
            locked.state, locked.error_code = (
                LiveSpotOrder.State.FAILED,
                getattr(error, "code", "permanent_validation"),
            )
            locked.save(update_fields=("state", "error_code", "updated_at"))
        return {"status": "failed"}
    except (AdapterError, TimeoutError, OSError):
        # The exchange may have accepted the order. Never resend automatically.
        with transaction.atomic():
            locked = LiveSpotOrder.objects.select_for_update().get(pk=order_id)
            locked.state, locked.error_code = LiveSpotOrder.State.UNCERTAIN, "unknown_outcome"
            locked.save(update_fields=("state", "error_code", "updated_at"))
        return {"status": "uncertain"}

    mapped = {
        OrderStatus.OPEN: LiveSpotOrder.State.OPEN,
        OrderStatus.PARTIAL: LiveSpotOrder.State.PARTIAL,
        OrderStatus.FILLED: LiveSpotOrder.State.FILLED,
        OrderStatus.CANCELLED: LiveSpotOrder.State.CANCELLED,
    }
    with transaction.atomic():
        locked = LiveSpotOrder.objects.select_for_update().get(pk=order_id)
        locked.external_order_id = receipt.order_id
        locked.filled_amount = receipt.filled_amount
        locked.average_price = receipt.average_price
        locked.state = mapped[receipt.status]
        locked.error_code = ""
        locked.save()
    return {"status": locked.state, "external_order_id": locked.external_order_id}
