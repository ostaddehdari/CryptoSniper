"""Explicit management for provider-created LIVE Spot trades.

An external observation is never managed automatically. The owner must adopt it
with explicit protection settings. This module never retries an uncertain exit.
"""

import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.audit import record_audit
from apps.exchanges.adapters import AdapterError, get_adapter
from apps.exchanges.models import ExchangeMarket, LiveSpotOrder
from apps.exchanges.security import get_account_credentials
from apps.exchanges.tasks import live_spot_order
from apps.marketdata.feeds import refresh_live_quote

from .models import (
    AccountControl,
    ExternalObservation,
    ExternalTradeManagement,
    RecoveryIssue,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def _decimal(value, *, required=False):
    if value in {None, ""}:
        if required:
            raise ValidationError("مقدار عددی لازم است.")
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValidationError("مقدار عددی معتبر نیست.") from error
    if not number.is_finite() or number <= ZERO:
        raise ValidationError("مقدار عددی باید مثبت باشد.")
    return number


def _side(payload):
    raw = str(
        payload.get("side")
        or payload.get("type")
        or payload.get("orderSide")
        or ""
    ).strip().lower()
    if raw in {"buy", "long", "2", "bid"}:
        return "buy"
    if raw in {"sell", "short", "1", "ask"}:
        return "sell"
    return ""


def normalize_external(observation):
    payload = observation.payload if isinstance(observation.payload, dict) else {}
    symbol = str(payload.get("symbol") or "").replace("_", "/").upper()
    if "/" not in symbol:
        for quote in ("USDT", "USDC", "BTC", "ETH"):
            if symbol.endswith(quote) and len(symbol) > len(quote):
                symbol = symbol[: -len(quote)] + "/" + quote
                break
    quantity = (
        payload.get("executedQty")
        or payload.get("dealVolume")
        or payload.get("filledAmount")
        or payload.get("quantity")
        or payload.get("amount")
        or payload.get("origQty")
        or payload.get("volume")
    )
    entry = (
        payload.get("averagePrice")
        or payload.get("avgPrice")
        or payload.get("dealPrice")
        or payload.get("price")
    )
    status = str(
        payload.get("status")
        or ("filled" if observation.kind == "fill" else "open")
    )
    return {
        "id": observation.pk,
        "account_id": observation.account_id,
        "exchange": observation.account.exchange.code,
        "account": observation.account.label,
        "kind": observation.kind,
        "external_id": observation.external_id,
        "symbol": symbol,
        "side": _side(payload),
        "entry_price": str(entry) if entry not in {None, ""} else None,
        "quantity": str(quantity) if quantity not in {None, ""} else None,
        "status": status,
        "observed_at": observation.observed_at,
        "payload": payload,
        "managed": hasattr(observation, "management"),
    }


def _targets(data):
    values = []
    for key in ("tp1", "tp2", "tp3"):
        value = _decimal(data.get(key))
        if value is not None:
            values.append((key, value))
    if (
        any(key == "tp3" for key, _ in values)
        and not any(key == "tp2" for key, _ in values)
    ):
        raise ValidationError("TP3 بدون TP2 معتبر نیست.")
    return values


def _validated_config(owner, observation, data):
    account = observation.account
    if account.owner_id != owner.pk:
        raise ValidationError("این معامله متعلق به کاربر دیگری است.")
    if (
        account.environment != "live"
        or account.status != "connected"
        or not account.trading_enabled
        or account.permissions.get("can_read") is not True
        or account.permissions.get("can_trade_spot") is not True
        or account.permissions.get("can_withdraw") is not False
    ):
        raise ValidationError("حساب Live برای مدیریت امن آماده نیست.")

    normalized = normalize_external(observation)
    if normalized["side"] != "buy":
        raise ValidationError("فعلاً فقط خرید Spot خارجی قابل مدیریت است.")
    if not normalized["symbol"]:
        raise ValidationError("نماد معامله خارجی قابل تشخیص نیست.")

    market = (
        ExchangeMarket.objects.filter(
            exchange=account.exchange,
            symbol=normalized["symbol"],
            market_type="spot",
            active=True,
        )
        .select_related("exchange")
        .first()
    )
    if not market:
        raise ValidationError("بازار Spot فعال برای این معامله پیدا نشد.")

    quantity = _decimal(
        data.get("quantity") or normalized["quantity"],
        required=True,
    )
    entry = _decimal(
        data.get("entry_price") or normalized["entry_price"],
        required=True,
    )
    stop = _decimal(data.get("stop_loss"))
    targets = _targets(data)
    if stop is not None and stop >= entry:
        raise ValidationError("برای خرید Spot، Stop باید پایین‌تر از Entry باشد.")
    prices = [value for _, value in targets]
    if prices and (
        any(value <= entry for value in prices)
        or prices != sorted(set(prices))
    ):
        raise ValidationError(
            "TPهای خرید باید بالاتر از Entry، صعودی و غیرتکراری باشند."
        )

    trailing = data.get("trailing_enabled") is True
    trailing_sl = data.get("trailing_sl_enabled") is True
    trigger = str(data.get("trailing_trigger", "tp1")).lower()
    if trigger not in {"tp1", "tp2", "tp3"}:
        raise ValidationError("شروع Trailing معتبر نیست.")
    target_map = dict(targets)
    if trailing and trigger not in target_map:
        raise ValidationError("برای Trigger انتخاب‌شده باید TP متناظر وارد شود.")
    if trailing_sl and "tp1" not in target_map:
        raise ValidationError(
            "Trailing SL برای انتقال Stop به Entry به TP1 نیاز دارد."
        )
    distance = _decimal(
        data.get("trailing_distance_percent") or "1",
        required=True,
    )
    if distance >= HUNDRED:
        raise ValidationError("فاصله Trailing باید کمتر از ۱۰۰٪ باشد.")

    return {
        "account": account,
        "market": market,
        "quantity": quantity,
        "entry_price": entry,
        "stop_loss": stop,
        "tp1": target_map.get("tp1"),
        "tp2": target_map.get("tp2"),
        "tp3": target_map.get("tp3"),
        "trailing_enabled": trailing,
        "trailing_sl_enabled": trailing_sl,
        "trailing_trigger": trigger,
        "trailing_distance_percent": distance,
    }


@transaction.atomic
def adopt_or_update(owner, observation_id, data):
    observation = (
        ExternalObservation.objects.select_for_update()
        .select_related("account", "account__exchange")
        .get(pk=observation_id, account__owner=owner)
    )
    config = _validated_config(owner, observation, data)
    item, created = (
        ExternalTradeManagement.objects.select_for_update().get_or_create(
            observation=observation,
            defaults={
                "owner": owner,
                "account": config["account"],
                "market": config["market"],
                "quantity": config["quantity"],
                "entry_price": config["entry_price"],
            },
        )
    )
    if not created and item.state in {
        ExternalTradeManagement.State.EXITING,
        ExternalTradeManagement.State.CLOSED,
    }:
        raise ValidationError(
            "معامله در حال خروج یا بسته‌شده قابل ویرایش نیست."
        )

    for field in (
        "account",
        "market",
        "quantity",
        "entry_price",
        "stop_loss",
        "tp1",
        "tp2",
        "tp3",
        "trailing_enabled",
        "trailing_sl_enabled",
        "trailing_trigger",
        "trailing_distance_percent",
    ):
        setattr(item, field, config[field])
    item.effective_stop = config["stop_loss"]
    item.state = ExternalTradeManagement.State.ACTIVE
    item.last_error = ""
    item.full_clean()
    item.save()
    record_audit(
        "external_trade.adopted" if created else "external_trade.updated",
        user=owner,
        metadata={
            "management_id": item.pk,
            "observation_id": observation.pk,
        },
    )
    return item


def serialize_management(item):
    if item is None:
        return None
    return {
        "id": item.pk,
        "state": item.state,
        "quantity": str(item.quantity),
        "entry_price": str(item.entry_price),
        "stop_loss": str(item.stop_loss) if item.stop_loss is not None else None,
        "effective_stop": (
            str(item.effective_stop)
            if item.effective_stop is not None
            else None
        ),
        "tp1": str(item.tp1) if item.tp1 is not None else None,
        "tp2": str(item.tp2) if item.tp2 is not None else None,
        "tp3": str(item.tp3) if item.tp3 is not None else None,
        "trailing_enabled": item.trailing_enabled,
        "trailing_sl_enabled": item.trailing_sl_enabled,
        "trailing_trigger": item.trailing_trigger,
        "trailing_distance_percent": str(item.trailing_distance_percent),
        "breakeven_moved": item.breakeven_moved,
        "high_water": (
            str(item.high_water) if item.high_water is not None else None
        ),
        "last_price": (
            str(item.last_price) if item.last_price is not None else None
        ),
        "last_tick_at": item.last_tick_at,
        "exit_order_id": item.exit_order_id,
        "last_error": item.last_error,
        "updated_at": item.updated_at,
    }


@transaction.atomic
def set_state(owner, observation_id, action):
    item = (
        ExternalTradeManagement.objects.select_for_update()
        .get(observation_id=observation_id, owner=owner)
    )
    if (
        action == "pause"
        and item.state == ExternalTradeManagement.State.ACTIVE
    ):
        item.state = ExternalTradeManagement.State.PAUSED
    elif (
        action == "resume"
        and item.state == ExternalTradeManagement.State.PAUSED
    ):
        item.state = ExternalTradeManagement.State.ACTIVE
    else:
        raise ValidationError("تغییر وضعیت مدیریت معامله مجاز نیست.")
    item.save(update_fields=("state", "updated_at"))
    record_audit(
        "external_trade." + action,
        user=owner,
        metadata={"management_id": item.pk},
    )
    return item


def _trigger_price(item):
    return {
        "tp1": item.tp1,
        "tp2": item.tp2,
        "tp3": item.tp3,
    }.get(item.trailing_trigger)


def _provider_free_base(item):
    adapter = get_adapter(
        item.account.exchange.adapter_code,
        credentials=get_account_credentials(item.account),
        environment=item.account.environment,
    )
    for balance in adapter.fetch_balance():
        if balance.asset.upper() == item.market.base_asset.symbol.upper():
            return balance.free
    return ZERO


def _exit_safety(item):
    control, _ = AccountControl.objects.get_or_create(account=item.account)
    return (
        item.account.status == "connected"
        and item.account.trading_enabled
        and item.account.permissions.get("can_trade_spot") is True
        and item.account.permissions.get("can_withdraw") is False
        and not control.paused
        and not RecoveryIssue.objects.filter(
            account=item.account,
            resolved=False,
        ).exists()
    )


def monitor_one(management_id):
    item = (
        ExternalTradeManagement.objects.select_related(
            "owner",
            "account",
            "account__exchange",
            "market",
            "exit_order",
        )
        .filter(pk=management_id)
        .first()
    )
    if not item:
        return "missing"
    if item.exit_order_id:
        state = item.exit_order.state
        if state == LiveSpotOrder.State.FILLED:
            ExternalTradeManagement.objects.filter(pk=item.pk).update(
                state=ExternalTradeManagement.State.CLOSED,
                updated_at=timezone.now(),
            )
            return "closed"
        if state in {
            LiveSpotOrder.State.FAILED,
            LiveSpotOrder.State.UNCERTAIN,
        }:
            ExternalTradeManagement.objects.filter(pk=item.pk).update(
                state=ExternalTradeManagement.State.ERROR,
                last_error=f"exit_{state}",
                updated_at=timezone.now(),
            )
            return "error"
        return "exiting"
    if item.state != ExternalTradeManagement.State.ACTIVE:
        return item.state

    quote_result = refresh_live_quote(item.market)
    quote = (
        quote_result.get("data")
        if isinstance(quote_result, dict)
        else None
    )
    if not quote or quote.get("stale") or not quote.get("price"):
        ExternalTradeManagement.objects.filter(pk=item.pk).update(
            last_error="live_quote_unavailable",
            updated_at=timezone.now(),
        )
        return "no_quote"
    price = Decimal(str(quote["price"]))
    effective = item.effective_stop
    breakeven = item.breakeven_moved
    high_water = item.high_water

    # Trailing SL: TP1 -> Entry exactly once, then it is finished.
    if (
        item.trailing_sl_enabled
        and not breakeven
        and item.tp1
        and price >= item.tp1
    ):
        effective = max(effective or ZERO, item.entry_price)
        breakeven = True

    # Trailing: selected TP activates percentage trailing.
    trigger = _trigger_price(item)
    if item.trailing_enabled and trigger and price >= trigger:
        high_water = max(high_water or price, price)
        derived = high_water * (
            Decimal("1") - item.trailing_distance_percent / HUNDRED
        )
        effective = max(effective or ZERO, derived)

    should_exit = (
        effective is not None
        and effective > ZERO
        and price <= effective
    )

    with transaction.atomic():
        locked = ExternalTradeManagement.objects.select_for_update().get(
            pk=item.pk
        )
        if (
            locked.exit_order_id
            or locked.state != ExternalTradeManagement.State.ACTIVE
        ):
            return locked.state
        locked.last_price = price
        locked.last_tick_at = timezone.now()
        locked.high_water = high_water
        locked.effective_stop = effective
        locked.breakeven_moved = breakeven
        locked.last_error = ""
        locked.save(
            update_fields=(
                "last_price",
                "last_tick_at",
                "high_water",
                "effective_stop",
                "breakeven_moved",
                "last_error",
                "updated_at",
            )
        )
        if not should_exit:
            return "monitored"
        if not _exit_safety(locked):
            locked.state = ExternalTradeManagement.State.ERROR
            locked.last_error = "safety_gate_closed"
            locked.save(
                update_fields=("state", "last_error", "updated_at")
            )
            return "safety_gate_closed"
        try:
            free_base = _provider_free_base(locked)
        except AdapterError:
            locked.state = ExternalTradeManagement.State.ERROR
            locked.last_error = "balance_read_failed"
            locked.save(update_fields=("state", "last_error", "updated_at"))
            return "balance_read_failed"
        if free_base < locked.quantity:
            locked.state = ExternalTradeManagement.State.ERROR
            locked.last_error = "insufficient_base_balance"
            locked.save(update_fields=("state", "last_error", "updated_at"))
            return "insufficient_base_balance"

        key = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"external-management-exit:{locked.pk}",
        )
        order, created = LiveSpotOrder.objects.get_or_create(
            owner=locked.owner,
            request_key=key,
            defaults={
                "account": locked.account,
                "market": locked.market,
                "client_order_id": (
                    f"cs-ext-exit-{locked.pk}-{key.hex[:18]}"
                ),
                "side": "sell",
                "order_type": "market",
                "amount": locked.quantity,
                "price": None,
            },
        )
        locked.exit_order = order
        locked.state = ExternalTradeManagement.State.EXITING
        locked.save(
            update_fields=("exit_order", "state", "updated_at")
        )
        if created:
            transaction.on_commit(
                lambda order_id=order.pk: live_spot_order.apply_async(
                    args=[order_id],
                    queue="orders",
                )
            )
        return "exit_queued"
