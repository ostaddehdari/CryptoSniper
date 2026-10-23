"""Managed protection for LIVE Spot entries created by CryptoSniper.

Entry orders are never submitted or retried here. Protection activates only
after the entry order is fully FILLED by the provider. Every managed exit is a
durable LiveSpotOrder with a deterministic request key.
"""

import uuid
from decimal import ROUND_DOWN, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.audit import record_audit
from apps.exchanges.adapters import AdapterError, get_adapter
from apps.exchanges.models import LiveSpotOrder
from apps.exchanges.security import get_account_credentials
from apps.exchanges.tasks import live_spot_order
from apps.marketdata.feeds import refresh_live_quote
from apps.tradeplans.models import TradePlan

from .models import (
    AccountControl,
    ManagedLiveExit,
    ManagedLiveTarget,
    ManagedLiveTrade,
    RecoveryIssue,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def _shares(plan):
    preview = plan.approved_snapshot or plan.preview or {}
    rows = preview.get("targets") or []
    values = []
    for index, key in enumerate(("tp1", "tp2", "tp3"), start=1):
        price = getattr(plan, key)
        if price is None:
            continue
        try:
            share = Decimal(str(rows[index - 1]["share_percent"]))
        except (IndexError, KeyError, TypeError, ValueError):
            count = sum(getattr(plan, name) is not None for name in ("tp1", "tp2", "tp3"))
            fallback = (
                [Decimal("100")]
                if count == 1
                else [Decimal("10"), Decimal("90")]
                if count == 2
                else [Decimal("10"), Decimal("10"), Decimal("80")]
            )
            share = fallback[index - 1]
        values.append((index, price, share))
    if not values or sum((row[2] for row in values), ZERO) != HUNDRED:
        raise ValidationError("توزیع TP برنامه معامله معتبر نیست.")
    return values


@transaction.atomic
def create_management(owner, plan_id, entry_order):
    plan = (
        TradePlan.objects.select_for_update()
        .select_related("exchange_account", "market")
        .get(pk=plan_id, owner=owner)
    )
    if (
        entry_order.owner_id != owner.pk
        or entry_order.account_id != plan.exchange_account_id
        or entry_order.market_id != plan.market_id
        or entry_order.side != "buy"
        or plan.side != TradePlan.Side.LONG
        or plan.market.market_type != "spot"
    ):
        raise ValidationError("برنامه مدیریت با سفارش Live هم‌خوان نیست.")
    if plan.status != TradePlan.Status.READY:
        raise ValidationError("برنامه معامله باید قبل از ارسال Live تأیید و ثابت شود.")

    item, created = ManagedLiveTrade.objects.get_or_create(
        entry_order=entry_order,
        defaults={
            "owner": owner,
            "account": entry_order.account,
            "market": entry_order.market,
            "plan": plan,
            "entry_price": plan.entry_price,
            "initial_stop": plan.stop_loss,
            "effective_stop": plan.stop_loss,
            "trailing_enabled": plan.percentage_trailing,
            "trailing_sl_enabled": plan.trailing_sl,
            "trailing_trigger": plan.percentage_trigger,
            "trailing_distance_percent": plan.trailing_distance,
        },
    )
    if not created:
        if item.plan_id != plan.pk:
            raise ValidationError("این سفارش قبلاً با برنامه دیگری مدیریت شده است.")
        return item

    ManagedLiveTarget.objects.bulk_create(
        [
            ManagedLiveTarget(
                management=item,
                position=position,
                price=price,
                share_percent=share,
            )
            for position, price, share in _shares(plan)
        ]
    )
    record_audit(
        "live_trade.management_created",
        user=owner,
        metadata={
            "management_id": item.pk,
            "entry_order_id": entry_order.pk,
            "plan_id": plan.pk,
        },
    )
    return item


def _floor_step(value, step):
    if not step or step <= ZERO:
        raise ValidationError("Lot Step بازار برای مدیریت Live موجود نیست.")
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


@transaction.atomic
def _activate_if_filled(management_id):
    item = (
        ManagedLiveTrade.objects.select_for_update()
        .select_related("entry_order", "market")
        .get(pk=management_id)
    )
    order = item.entry_order
    if item.state != ManagedLiveTrade.State.PENDING_ENTRY:
        return item.state

    if order.state in {
        LiveSpotOrder.State.FAILED,
        LiveSpotOrder.State.CANCELLED,
        LiveSpotOrder.State.UNCERTAIN,
    }:
        item.state = ManagedLiveTrade.State.ERROR
        item.last_error = f"entry_{order.state}"
        item.save(update_fields=("state", "last_error", "updated_at"))
        return item.state
    if order.state != LiveSpotOrder.State.FILLED:
        return ManagedLiveTrade.State.PENDING_ENTRY
    if order.filled_amount <= ZERO or order.filled_amount != order.amount:
        item.state = ManagedLiveTrade.State.ERROR
        item.last_error = "entry_fill_quantity_invalid"
        item.save(update_fields=("state", "last_error", "updated_at"))
        return item.state

    quantity = order.filled_amount
    item.initial_quantity = quantity
    item.remaining_quantity = quantity
    item.entry_price = order.average_price or order.price or item.entry_price
    item.effective_stop = item.initial_stop
    item.state = ManagedLiveTrade.State.ACTIVE
    item.last_error = ""

    targets = list(
        ManagedLiveTarget.objects.select_for_update()
        .filter(management=item)
        .order_by("position")
    )
    allocated = ZERO
    for target in targets:
        if target.position == targets[-1].position:
            target.allocated_quantity = quantity - allocated
        else:
            target.allocated_quantity = _floor_step(
                quantity * target.share_percent / HUNDRED,
                item.market.amount_step,
            )
            allocated += target.allocated_quantity
        target.state = (
            ManagedLiveTarget.State.WAITING
            if target.allocated_quantity > ZERO
            else ManagedLiveTarget.State.SKIPPED
        )
        target.save(update_fields=("allocated_quantity", "state", "updated_at"))

    if sum((target.allocated_quantity for target in targets), ZERO) != quantity:
        raise ValidationError("تخصیص حجم TP با مقدار Filled ورود برابر نیست.")

    item.save(
        update_fields=(
            "initial_quantity",
            "remaining_quantity",
            "entry_price",
            "effective_stop",
            "state",
            "last_error",
            "updated_at",
        )
    )
    record_audit(
        "live_trade.management_activated",
        user=item.owner,
        metadata={
            "management_id": item.pk,
            "entry_order_id": order.pk,
            "quantity": str(quantity),
        },
    )
    return item.state


def _provider_free_base(item):
    adapter = get_adapter(
        item.account.exchange.adapter_code,
        credentials=get_account_credentials(item.account),
        environment=item.account.environment,
    )
    symbol = item.market.base_asset.symbol.upper()
    for balance in adapter.fetch_balance():
        if balance.asset.upper() == symbol:
            return balance.free
    return ZERO


def _safety(item):
    control, _ = AccountControl.objects.get_or_create(account=item.account)
    return (
        settings.LIVE_TRADING_ENABLED
        and item.account.environment == "live"
        and item.account.status == "connected"
        and item.account.trading_enabled
        and item.account.permissions.get("can_read") is True
        and item.account.permissions.get("can_trade_spot") is True
        and item.account.permissions.get("can_withdraw") is False
        and not control.paused
        and not RecoveryIssue.objects.filter(
            account=item.account,
            resolved=False,
        ).exists()
    )


def _deterministic_key(kind, management_id, position=None):
    suffix = f":{position}" if position is not None else ""
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"cryptosniper-managed-live:{kind}:{management_id}{suffix}",
    )


def _create_exit_order(item, *, amount, key, label):
    if amount <= ZERO or amount > item.remaining_quantity:
        raise ValidationError("حجم خروج مدیریت Live معتبر نیست.")
    free_base = _provider_free_base(item)
    if free_base < amount:
        raise ValidationError("موجودی آزاد Base برای خروج مدیریت‌شده کافی نیست.")
    order, created = LiveSpotOrder.objects.get_or_create(
        owner=item.owner,
        request_key=key,
        defaults={
            "account": item.account,
            "market": item.market,
            "client_order_id": f"cs-{label}-{item.pk}-{key.hex[:16]}",
            "side": "sell",
            "order_type": "market",
            "amount": amount,
            "price": None,
        },
    )
    if created:
        transaction.on_commit(
            lambda order_id=order.pk: live_spot_order.apply_async(
                args=[order_id],
                queue="orders",
            )
        )
    return order


@transaction.atomic
def _consume_target_results(management_id):
    item = (
        ManagedLiveTrade.objects.select_for_update()
        .select_related("account", "market")
        .get(pk=management_id)
    )
    targets = list(
        ManagedLiveTarget.objects.select_for_update()
        .select_related("exit_order")
        .filter(management=item)
        .order_by("position")
    )
    changed = False
    for target in targets:
        order = target.exit_order
        if not order or target.state != ManagedLiveTarget.State.EXIT_PENDING:
            continue
        if order.state == LiveSpotOrder.State.FILLED:
            filled = min(order.filled_amount, item.remaining_quantity)
            item.remaining_quantity -= filled
            target.state = ManagedLiveTarget.State.FILLED
            changed = True
        elif order.state in {
            LiveSpotOrder.State.FAILED,
            LiveSpotOrder.State.UNCERTAIN,
            LiveSpotOrder.State.CANCELLED,
        }:
            item.state = ManagedLiveTrade.State.ERROR
            item.last_error = f"tp{target.position}_exit_{order.state}"
            changed = True
            break
        else:
            return "target_exit_pending"

    if item.remaining_quantity == ZERO and item.state != ManagedLiveTrade.State.ERROR:
        item.state = ManagedLiveTrade.State.CLOSED
        for target in targets:
            if target.state == ManagedLiveTarget.State.WAITING:
                target.state = ManagedLiveTarget.State.SKIPPED
                target.save(update_fields=("state", "updated_at"))
        changed = True

    if changed:
        for target in targets:
            if target.pk:
                target.save(update_fields=("state", "updated_at"))
        item.save(
            update_fields=(
                "remaining_quantity",
                "state",
                "last_error",
                "updated_at",
            )
        )
    return item.state


@transaction.atomic
def _consume_full_exit(management_id):
    item = (
        ManagedLiveTrade.objects.select_for_update()
        .select_related("full_exit__order")
        .filter(pk=management_id)
        .first()
    )
    if not item or not hasattr(item, "full_exit"):
        return None
    order = item.full_exit.order
    if order.state == LiveSpotOrder.State.FILLED:
        item.remaining_quantity = ZERO
        item.state = ManagedLiveTrade.State.CLOSED
        item.last_error = ""
        ManagedLiveTarget.objects.filter(
            management=item,
            state=ManagedLiveTarget.State.WAITING,
        ).update(state=ManagedLiveTarget.State.SKIPPED)
        item.save(
            update_fields=(
                "remaining_quantity",
                "state",
                "last_error",
                "updated_at",
            )
        )
        return item.state
    if order.state in {
        LiveSpotOrder.State.FAILED,
        LiveSpotOrder.State.UNCERTAIN,
        LiveSpotOrder.State.CANCELLED,
    }:
        item.state = ManagedLiveTrade.State.ERROR
        item.last_error = f"full_exit_{order.state}"
        item.save(update_fields=("state", "last_error", "updated_at"))
        return item.state
    return ManagedLiveTrade.State.EXITING


def _trigger_price(item, targets):
    wanted = {"tp1": 1, "tp2": 2, "tp3": 3}[item.trailing_trigger]
    for target in targets:
        if target.position == wanted:
            return target.price
    return None


def serialize_management(item):
    if item is None:
        return None
    targets = list(item.targets.all().order_by("position"))
    return {
        "id": item.pk,
        "state": item.state,
        "entry_order_id": item.entry_order_id,
        "plan_id": item.plan_id,
        "initial_quantity": str(item.initial_quantity),
        "remaining_quantity": str(item.remaining_quantity),
        "entry_price": str(item.entry_price),
        "initial_stop": str(item.initial_stop),
        "effective_stop": str(item.effective_stop),
        "trailing_enabled": item.trailing_enabled,
        "trailing_sl_enabled": item.trailing_sl_enabled,
        "trailing_trigger": item.trailing_trigger,
        "trailing_distance_percent": str(item.trailing_distance_percent),
        "breakeven_moved": item.breakeven_moved,
        "high_water": str(item.high_water) if item.high_water is not None else None,
        "last_price": str(item.last_price) if item.last_price is not None else None,
        "last_tick_at": item.last_tick_at,
        "last_error": item.last_error,
        "targets": [
            {
                "position": target.position,
                "price": str(target.price),
                "share_percent": str(target.share_percent),
                "allocated_quantity": str(target.allocated_quantity),
                "state": target.state,
                "exit_order_id": target.exit_order_id,
            }
            for target in targets
        ],
    }


def monitor_one(management_id):
    item = (
        ManagedLiveTrade.objects.select_related(
            "owner",
            "account",
            "account__exchange",
            "market",
            "market__base_asset",
            "entry_order",
            "plan",
        )
        .prefetch_related("targets")
        .filter(pk=management_id)
        .first()
    )
    if not item:
        return "missing"

    if item.state == ManagedLiveTrade.State.PENDING_ENTRY:
        state = _activate_if_filled(item.pk)
        if state != ManagedLiveTrade.State.ACTIVE:
            return state
        item.refresh_from_db()

    full_state = _consume_full_exit(item.pk)
    if full_state is not None:
        return full_state

    target_state = _consume_target_results(item.pk)
    if target_state in {
        "target_exit_pending",
        ManagedLiveTrade.State.CLOSED,
        ManagedLiveTrade.State.ERROR,
    }:
        return target_state

    item.refresh_from_db()
    if item.state != ManagedLiveTrade.State.ACTIVE:
        return item.state
    if item.remaining_quantity <= ZERO:
        ManagedLiveTrade.objects.filter(pk=item.pk).update(
            state=ManagedLiveTrade.State.CLOSED,
            updated_at=timezone.now(),
        )
        return ManagedLiveTrade.State.CLOSED

    quote_result = refresh_live_quote(item.market)
    quote = quote_result.get("data") if isinstance(quote_result, dict) else None
    if not quote or quote.get("stale") or not quote.get("price"):
        ManagedLiveTrade.objects.filter(pk=item.pk).update(
            last_error="live_quote_unavailable",
            updated_at=timezone.now(),
        )
        return "no_quote"
    price = Decimal(str(quote["price"]))
    targets = list(item.targets.all().order_by("position"))
    tp1 = next((target for target in targets if target.position == 1), None)

    effective = item.effective_stop
    high_water = item.high_water
    breakeven = item.breakeven_moved

    if (
        item.trailing_sl_enabled
        and not breakeven
        and tp1
        and price >= tp1.price
    ):
        effective = max(effective, item.entry_price)
        breakeven = True

    trigger = _trigger_price(item, targets)
    if item.trailing_enabled and trigger and price >= trigger:
        high_water = max(high_water or price, price)
        derived = high_water * (
            Decimal("1") - item.trailing_distance_percent / HUNDRED
        )
        effective = max(effective, derived)

    stop_hit = price <= effective

    with transaction.atomic():
        locked = (
            ManagedLiveTrade.objects.select_for_update()
            .select_related("account", "market")
            .get(pk=item.pk)
        )
        if locked.state != ManagedLiveTrade.State.ACTIVE:
            return locked.state
        locked.last_price = price
        locked.last_tick_at = timezone.now()
        locked.effective_stop = effective
        locked.high_water = high_water
        locked.breakeven_moved = breakeven
        locked.last_error = ""
        locked.save(
            update_fields=(
                "last_price",
                "last_tick_at",
                "effective_stop",
                "high_water",
                "breakeven_moved",
                "last_error",
                "updated_at",
            )
        )

        if stop_hit:
            if not _safety(locked):
                locked.state = ManagedLiveTrade.State.ERROR
                locked.last_error = "safety_gate_closed"
                locked.save(update_fields=("state", "last_error", "updated_at"))
                return "safety_gate_closed"
            try:
                order = _create_exit_order(
                    locked,
                    amount=locked.remaining_quantity,
                    key=_deterministic_key("full-exit", locked.pk),
                    label="managed-stop",
                )
            except (AdapterError, ValidationError) as error:
                locked.state = ManagedLiveTrade.State.ERROR
                locked.last_error = getattr(error, "code", "managed_exit_rejected")[:80]
                locked.save(update_fields=("state", "last_error", "updated_at"))
                return locked.last_error
            ManagedLiveExit.objects.get_or_create(
                management=locked,
                defaults={"reason": "stop_or_trailing", "order": order},
            )
            locked.state = ManagedLiveTrade.State.EXITING
            locked.save(update_fields=("state", "updated_at"))
            return "full_exit_queued"

        if not locked.trailing_enabled:
            for target in (
                ManagedLiveTarget.objects.select_for_update()
                .filter(
                    management=locked,
                    state=ManagedLiveTarget.State.WAITING,
                    price__lte=price,
                )
                .order_by("position")
            ):
                amount = min(target.allocated_quantity, locked.remaining_quantity)
                if amount <= ZERO:
                    target.state = ManagedLiveTarget.State.SKIPPED
                    target.save(update_fields=("state", "updated_at"))
                    continue
                if not _safety(locked):
                    locked.state = ManagedLiveTrade.State.ERROR
                    locked.last_error = "safety_gate_closed"
                    locked.save(update_fields=("state", "last_error", "updated_at"))
                    return "safety_gate_closed"
                try:
                    order = _create_exit_order(
                        locked,
                        amount=amount,
                        key=_deterministic_key(
                            "target-exit",
                            locked.pk,
                            target.position,
                        ),
                        label=f"managed-tp{target.position}",
                    )
                except (AdapterError, ValidationError) as error:
                    locked.state = ManagedLiveTrade.State.ERROR
                    locked.last_error = getattr(
                        error,
                        "code",
                        "managed_target_exit_rejected",
                    )[:80]
                    locked.save(update_fields=("state", "last_error", "updated_at"))
                    return locked.last_error
                target.exit_order = order
                target.state = ManagedLiveTarget.State.EXIT_PENDING
                target.save(update_fields=("exit_order", "state", "updated_at"))
                return f"tp{target.position}_exit_queued"

    return "monitored"
