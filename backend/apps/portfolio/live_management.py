"""Durable Spot-long exits. No decisions use the display candle/quote cache."""

import uuid
from decimal import ROUND_DOWN, Decimal, localcontext

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.audit import record_audit
from apps.exchanges.adapters import AdapterError
from apps.exchanges.live_orders import queue_live_spot_order
from apps.exchanges.models import BalanceSnapshot, LiveSpotOrder, UserExchangeAccount
from apps.exchanges.reconciliation import TERMINAL, account_adapter, reconcile_order
from apps.operations.models import LiveExitAttempt, ManagedSpotPosition

ZERO = Decimal("0")


def enabled():
    return settings.LIVE_TRADING_ENABLED and settings.LIVE_EXIT_MANAGEMENT_ENABLED


def _floor(value, step):
    if not step or step <= 0:
        raise ValidationError("دقت بازار مشخص نیست.")
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def create_entry_position(order, snapshot):
    if not enabled() or order.side != "buy" or order.market.market_type != "spot":
        raise ValidationError("مدیریت خروج Spot فعال و مجاز نیست.")
    position, _ = ManagedSpotPosition.objects.get_or_create(
        entry_order=order,
        defaults={
            "account": order.account,
            "market": order.market,
            "snapshot": snapshot,
            "effective_stop": Decimal(snapshot["stop_loss"]),
            "acquired": order.filled_amount,
            "state": "active" if order.filled_amount else "waiting_entry",
        },
    )
    return position


def _inventory(position):
    if position.entry_order_id:
        position.entry_order.refresh_from_db()
        position.acquired = position.entry_order.filled_amount
        if position.inventory_cap is not None:
            position.acquired = min(position.acquired, position.inventory_cap)
    exited = position.exits.aggregate(value=Sum("order__filled_amount"))["value"] or ZERO
    if exited > position.acquired:
        raise ValidationError("رسید خروج از موجودی تأییدشده بیشتر است؛ بررسی لازم است.")
    position.exited = exited
    if position.remaining == 0:
        terminal_entry = not position.entry_order_id or position.entry_order.state in TERMINAL
        position.state = (
            ("closed" if position.acquired else "cancelled") if terminal_entry else "waiting_entry"
        )
    else:
        position.state = "active"


def _fresh_inputs(adapter, market):
    ticker = adapter.fetch_ticker(market.symbol)
    age = (timezone.now() - ticker.observed_at).total_seconds()
    if ticker.symbol.upper() != market.symbol.upper() or not -5 <= age <= 25:
        raise ValidationError("قیمت صرافی تازه یا هم‌نماد نیست.")
    if not ticker.price.is_finite() or ticker.price <= 0:
        raise ValidationError("قیمت صرافی معتبر نیست.")
    balances = adapter.fetch_balance()
    matches = [b for b in balances if b.asset.upper() == market.base_asset.symbol]
    if len(matches) != 1 or not matches[0].free.is_finite() or matches[0].free < 0:
        raise ValidationError("موجودی آزاد تازهٔ ارز پایه مشخص نیست.")
    return ticker, matches[0]


def _protection(position, price):
    snapshot = position.snapshot
    targets = snapshot["targets"]
    if (
        snapshot.get("trailing_sl")
        and not position.break_even_applied
        and price >= Decimal(targets[0]["price"])
    ):
        position.effective_stop = max(position.effective_stop, Decimal(snapshot["entry_price"]))
        position.break_even_applied = True
    if not snapshot.get("percentage_trailing"):
        return
    trigger = int(snapshot.get("trailing_trigger", "tp1")[-1])
    if trigger > len(targets) or trigger < 1:
        raise ValidationError("هدف شروع Trailing معتبر نیست.")
    # Once armed, high-water keeps advancing even after price drops below the trigger.
    if price >= Decimal(targets[trigger - 1]["price"]):
        position.trailing_active = True
    if position.trailing_active:
        position.high_water = max(position.high_water or price, price)
        distance = Decimal(snapshot["trailing_distance_percent"])
        if not 0 < distance < 100:
            raise ValidationError("فاصله Trailing معتبر نیست.")
        derived = _floor(position.high_water * (100 - distance) / 100, position.market.price_step)
        position.effective_stop = max(position.effective_stop, derived)


def _intent(position, price):
    if position.exit_latched or price <= position.effective_stop:
        position.exit_latched = True
        return "sl", position.remaining
    targets = position.snapshot["targets"]
    trailing = position.snapshot.get("percentage_trailing", False)
    trigger = int(position.snapshot.get("trailing_trigger", "tp1")[-1])
    due, shares = None, ZERO
    for index, target in enumerate(targets, 1):
        if trailing and index >= trigger:
            break
        shares += Decimal(target["share_percent"])
        if price >= Decimal(target["price"]):
            due = (index, shares)
    if not due:
        return None
    index, shares = due
    already = (
        position.exits.filter(reason__startswith="tp").aggregate(value=Sum("order__filled_amount"))[
            "value"
        ]
        or ZERO
    )
    wanted = (
        position.acquired
        if index == len(targets)
        else _floor(position.acquired * shares / 100, position.market.amount_step)
    )
    return f"tp{index}", min(position.remaining, max(ZERO, wanted - already))


def _reserved(account, asset_id):
    # Provider free already excludes OPEN/PARTIAL locked orders. Unsent/unknown writes
    # still reserve here, so two positions cannot race the same free inventory.
    orders = LiveSpotOrder.objects.filter(
        account=account,
        market__base_asset_id=asset_id,
        side="sell",
        state__in=("pending", "submitting", "uncertain"),
    )
    return sum((o.amount - o.filled_amount for o in orders), ZERO)


@transaction.atomic
def _decide(position_id, ticker, balance):
    # All management mutations lock account first, then position, then order rows.
    account_id = ManagedSpotPosition.objects.values_list("account_id", flat=True).get(
        pk=position_id
    )
    account = UserExchangeAccount.objects.select_for_update().get(pk=account_id)
    position = (
        ManagedSpotPosition.objects.select_for_update(of=("self",))
        .select_related("account__owner", "market__base_asset", "entry_order")
        .get(pk=position_id)
    )
    _inventory(position)
    position.last_checked_at = timezone.now()
    if not -5 <= (timezone.now() - ticker.observed_at).total_seconds() <= 25:
        raise ValidationError("قیمت هنگام تصمیم‌گیری تازه نیست.")
    if position.paused or not enabled() or position.state == "closed":
        position.save()
        return {"status": "paused" if position.paused else position.state}
    position.last_price, position.last_price_at = ticker.price, ticker.observed_at
    position.error_code = ""
    _protection(position, ticker.price)
    intent = _intent(position, ticker.price) if position.remaining > 0 else None
    active = position.exits.exclude(order__state__in=TERMINAL).select_related("order").first()
    if active:
        position.state = "uncertain" if active.order.state == "uncertain" else "closing"
        position.save()
        if (
            intent
            and intent[0] == "sl"
            and (
                active.reason.startswith("tp")
                or (
                    active.reason == "sl"
                    and active.order.state in {"open", "partial"}
                    and active.order.price > ticker.price
                )
            )
        ):
            if active.order.state == "pending":
                LiveSpotOrder.objects.filter(pk=active.order_id, state="pending").update(
                    state="cancelled", error_code="superseded_by_stop"
                )
            elif active.order.external_order_id:
                return {"status": "cancel_exit", "order_id": active.order_id}
        return {"status": position.state}
    failed = position.exits.filter(order__state="failed").order_by("-sequence").first()
    if failed and failed.sequence == position.exit_sequence:
        position.state, position.error_code = "review", "exit_failed_review_required"
        position.save()
        return {"status": "review"}
    if not intent or intent[1] <= 0:
        position.save()
        return {"status": position.state}
    if position.entry_order_id and position.entry_order.state not in TERMINAL:
        position.save()
        if position.entry_order.state == "pending":
            LiveSpotOrder.objects.filter(pk=position.entry_order_id, state="pending").update(
                state="cancelled"
            )
            return {"status": "entry_cancelled_locally"}
        return {"status": "cancel_entry", "order_id": position.entry_order_id}
    reason, wanted = intent
    amount = _floor(wanted, position.market.amount_step)
    price = _floor(ticker.price, position.market.price_step)
    if (
        amount <= 0
        or (position.market.min_amount and amount < position.market.min_amount)
        or (position.market.min_notional and amount * price < position.market.min_notional)
    ):
        if reason == "sl" or wanted == position.remaining:
            position.state, position.error_code = "dust", "remaining_below_exchange_minimum"
        position.save()
        return {"status": "below_minimum"}
    free = balance.free - _reserved(account, position.market.base_asset_id)
    if amount > free:
        position.state, position.error_code = "review", "base_balance_or_fee_shortfall"
        position.save()
        return {"status": "review"}
    BalanceSnapshot.objects.create(
        exchange_account=account,
        asset=position.market.base_asset,
        wallet_scope="spot",
        free_balance=balance.free,
        locked_balance=balance.locked,
        total_balance=balance.total,
        captured_at=timezone.now(),
    )
    position.exit_sequence += 1
    order, _ = queue_live_spot_order(
        position.account.owner,
        account,
        {
            "request_key": uuid.uuid4(),
            "market": position.market,
            "side": "sell",
            "amount": amount,
            "price": price,
            "protective_exit": True,
        },
    )
    LiveExitAttempt.objects.create(
        position=position,
        order=order,
        sequence=position.exit_sequence,
        reason=reason,
        trigger_price=ticker.price,
    )
    position.state = "closing"
    position.save()
    record_audit(
        "live.exit_queued",
        user=position.account.owner,
        metadata={"position_id": position.pk, "order_id": order.pk, "reason": reason},
    )
    from apps.tradeplans.submission import _dispatch

    transaction.on_commit(lambda: _dispatch(order.pk))
    return {"status": "exit_queued", "order_id": order.pk}


@transaction.atomic
def sync_inventory(position_id):
    account_id = ManagedSpotPosition.objects.values_list("account_id", flat=True).get(
        pk=position_id
    )
    UserExchangeAccount.objects.select_for_update().get(pk=account_id)
    position = (
        ManagedSpotPosition.objects.select_for_update(of=("self",))
        .select_related("entry_order")
        .get(pk=position_id)
    )
    _inventory(position)
    position.last_checked_at = timezone.now()
    position.save()
    return position


def monitor_position(position_id):
    position = ManagedSpotPosition.objects.select_related(
        "account__exchange", "market__base_asset", "entry_order"
    ).get(pk=position_id)
    try:
        adapter = account_adapter(position.account)
        # Read reconciliation runs even when a strategy is paused or its feed is down.
        if position.entry_order_id and position.entry_order.state not in TERMINAL:
            reconcile_order(position.entry_order_id, adapter=adapter)
        for pk in position.exits.exclude(order__state__in=TERMINAL).values_list(
            "order_id", flat=True
        ):
            reconcile_order(pk, adapter=adapter)
        position = sync_inventory(position_id)
        if position.state in {"closed", "cancelled"}:
            return {"status": position.state}
        if not enabled():
            return {"status": "safety_gate_closed"}
        ticker, balance = _fresh_inputs(adapter, position.market)
        with localcontext() as context:
            context.prec = 60
            result = _decide(position_id, ticker, balance)
        if result["status"] in {"cancel_entry", "cancel_exit"}:
            reconcile_order(result["order_id"], adapter=adapter, cancel=True)
            return {"status": "cancellation_checked"}
        return result
    except (AdapterError, ValidationError, ValueError, ArithmeticError, OSError, TimeoutError):
        ManagedSpotPosition.objects.filter(pk=position_id).update(
            error_code="feed_or_receipt_unavailable", last_checked_at=timezone.now()
        )
        return {"status": "waiting_evidence"}
