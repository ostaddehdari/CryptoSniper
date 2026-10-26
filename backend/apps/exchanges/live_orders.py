"""Durable, explicitly-confirmed Spot writes for verified no-withdrawal keys."""

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .adapters import (
    AdapterError,
    AuthenticationError,
    InvalidProviderResponse,
    OrderStatus,
    UnsupportedOperationError,
    get_adapter,
)
from .models import LiveSpotOrder, UserExchangeAccount
from .security import get_account_credentials


def _number(value, label):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValidationError(f"{label} معتبر نیست.") from error
    if not number.is_finite() or number <= 0:
        raise ValidationError(f"{label} باید مثبت باشد.")
    return number


def validate_live_spot_intent(account, market, *, side, amount, price):
    """Re-check every invariant at the durable boundary, not only in HTML forms."""
    amount = _number(amount, "مقدار")
    price = _number(price, "قیمت")
    if (
        account.environment != UserExchangeAccount.Environment.LIVE
        or account.status != UserExchangeAccount.Status.CONNECTED
        or not account.trading_enabled
        or account.permissions.get("can_read") is not True
        or account.permissions.get("can_trade_spot") is not True
        or account.permissions.get("can_withdraw") is not False
    ):
        raise ValidationError("حساب Live با Read+Spot و Withdrawal خاموش لازم است.")
    if side not in {"buy", "sell"}:
        raise ValidationError("جهت سفارش Spot معتبر نیست.")
    if (
        market.exchange_id != account.exchange_id
        or market.market_type != "spot"
        or not market.active
    ):
        raise ValidationError("بازار Spot فعال متعلق به همین اتصال لازم است.")
    if not market.amount_step or market.amount_step <= 0:
        raise ValidationError("Lot Step بازار همگام نشده است.")
    if amount % market.amount_step:
        raise ValidationError("مقدار سفارش با Lot Step صرافی سازگار نیست.")
    if market.price_step and price % market.price_step:
        raise ValidationError("قیمت سفارش با Tick Size صرافی سازگار نیست.")
    if market.min_amount and amount < market.min_amount:
        raise ValidationError("مقدار سفارش از حداقل بازار کمتر است.")
    if market.max_amount and amount > market.max_amount:
        raise ValidationError("مقدار سفارش از سقف بازار بیشتر است.")
    notional = amount * price
    if market.min_notional and notional < market.min_notional:
        raise ValidationError("ارزش سفارش از Min Notional صرافی کمتر است.")

    asset_id = market.quote_asset_id if side == "buy" else market.base_asset_id
    balance = (
        account.balance_snapshots.filter(asset_id=asset_id, wallet_scope="spot")
        .order_by("-captured_at")
        .first()
    )
    if not balance or balance.captured_at < timezone.now() - timedelta(minutes=15):
        raise ValidationError("موجودی تازه نیست؛ ابتدا حساب صرافی را همگام‌سازی کنید.")
    if side == "buy":
        fee_rate = market.taker_fee or Decimal("0")
        required = notional * (Decimal("1") + fee_rate)
    else:
        required = amount
    if balance.free_balance < required:
        raise ValidationError("موجودی آزاد برای این سفارش کافی نیست.")
    return amount, price


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
        if (
            existing.account_id != account.pk
            or existing.market_id != cleaned["market"].pk
            or existing.side != cleaned["side"]
            or existing.amount != Decimal(str(cleaned["amount"]))
            or existing.price != Decimal(str(cleaned["price"]))
        ):
            raise ValidationError("این شناسه قبلاً برای مشخصات سفارش دیگری استفاده شده است.")
        return existing, False
    if not settings.LIVE_TRADING_ENABLED:
        raise ValidationError("Live trading روی سرور خاموش است.")
    from apps.operations.models import AccountControl

    if AccountControl.objects.filter(account=account, paused=True).exists():
        raise ValidationError("ورود جدید این حساب در وضعیت سیستم متوقف شده است.")
    market = cleaned["market"]
    amount, price = validate_live_spot_intent(
        account,
        market,
        side=cleaned["side"],
        amount=cleaned["amount"],
        price=cleaned["price"],
    )
    order = LiveSpotOrder.objects.create(
        owner=owner,
        account=account,
        market=market,
        request_key=request_key,
        source_plan=cleaned.get("source_plan"),
        client_order_id=f"cs-live-{owner.pk}-{request_key.hex[:24]}",
        side=cleaned["side"],
        order_type="limit",
        amount=amount,
        price=price,
    )
    return order, True


def _validate_receipt(order, receipt):
    if receipt.status not in {
        OrderStatus.OPEN,
        OrderStatus.PARTIAL,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
    }:
        raise InvalidProviderResponse("provider_unknown_order_status")
    if receipt.symbol.upper() != order.market.symbol.upper():
        raise InvalidProviderResponse("provider_order_symbol_mismatch")
    if receipt.side.lower() != order.side:
        raise InvalidProviderResponse("provider_order_side_mismatch")
    if receipt.amount != order.amount:
        raise InvalidProviderResponse("provider_order_amount_mismatch")
    if (
        not receipt.filled_amount.is_finite()
        or receipt.filled_amount < 0
        or receipt.filled_amount > order.amount
    ):
        raise InvalidProviderResponse("provider_order_fill_invalid")
    if receipt.client_order_id and receipt.client_order_id != order.client_order_id:
        raise InvalidProviderResponse("provider_client_order_id_mismatch")
    if receipt.filled_amount > 0 and (
        receipt.average_price is None
        or not receipt.average_price.is_finite()
        or receipt.average_price <= 0
    ):
        raise InvalidProviderResponse("provider_fill_price_missing")
    if not receipt.order_id:
        raise InvalidProviderResponse("provider_order_id_missing")


def execute_live_spot_order(order_id):
    with transaction.atomic():
        order = (
            LiveSpotOrder.objects.select_for_update()
            .select_related(
                "account__exchange",
                "market__base_asset",
                "market__quote_asset",
            )
            .get(pk=order_id)
        )
        if order.state != LiveSpotOrder.State.PENDING:
            return {"status": order.state}
        if not settings.LIVE_TRADING_ENABLED:
            order.state, order.error_code = LiveSpotOrder.State.FAILED, "live_disabled"
            order.save(update_fields=("state", "error_code", "updated_at"))
            return {"status": "failed"}
        try:
            validate_live_spot_intent(
                order.account,
                order.market,
                side=order.side,
                amount=order.amount,
                price=order.price,
            )
        except ValidationError:
            order.state, order.error_code = LiveSpotOrder.State.FAILED, "safety_gate_closed"
            order.save(update_fields=("state", "error_code", "updated_at"))
            return {"status": "failed"}
        order.state = LiveSpotOrder.State.SUBMITTING
        order.save(update_fields=("state", "updated_at"))

    placement_started = False
    try:
        adapter = get_adapter(
            order.account.exchange.adapter_code,
            credentials=get_account_credentials(order.account),
            environment=order.account.environment,
        )
        permission = adapter.validate_credentials()
        if (
            permission.can_read is not True
            or permission.can_trade_spot is not True
            or permission.can_withdraw is not False
        ):
            raise ValidationError("مجوز Read+Spot بدون برداشت دیگر تأیید نمی‌شود.")
        placement_started = True
        receipt = adapter.place_order(
            client_order_id=order.client_order_id,
            symbol=order.market.symbol,
            side=order.side,
            order_type=order.order_type,
            amount=order.amount,
            price=order.price,
        )
        _validate_receipt(order, receipt)
    except (
        AuthenticationError,
        InvalidProviderResponse,
        UnsupportedOperationError,
        ValidationError,
        ValueError,
        TypeError,
    ) as error:
        with transaction.atomic():
            locked = LiveSpotOrder.objects.select_for_update().get(pk=order_id)
            locked.state, locked.error_code = (
                LiveSpotOrder.State.UNCERTAIN if placement_started else LiveSpotOrder.State.FAILED,
                getattr(error, "code", "permanent_validation"),
            )
            locked.save(update_fields=("state", "error_code", "updated_at"))
        return {"status": locked.state}
    except (AdapterError, TimeoutError, OSError):
        # Provider may have accepted the request. Never submit a second copy automatically.
        with transaction.atomic():
            locked = LiveSpotOrder.objects.select_for_update().get(pk=order_id)
            locked.state, locked.error_code = LiveSpotOrder.State.UNCERTAIN, "unknown_outcome"
            locked.save(update_fields=("state", "error_code", "updated_at"))
        return {"status": "uncertain"}

    from .reconciliation import apply_receipt

    locked = apply_receipt(order_id, receipt)
    return {"status": locked.state, "external_order_id": locked.external_order_id}
