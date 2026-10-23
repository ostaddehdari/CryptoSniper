import uuid
from decimal import ROUND_DOWN, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.audit import record_audit
from apps.exchanges.adapters import AdapterError, get_adapter
from apps.exchanges.live_orders import queue_live_spot_order
from apps.exchanges.security import get_account_credentials
from apps.exchanges.tasks import live_spot_order
from apps.operations.models import ExternalObservation, ExternalTradePolicy


@transaction.atomic
def apply_external_policy(owner, observation_id, data):
    item = (
        ExternalObservation.objects.select_for_update()
        .select_related("account__exchange")
        .get(pk=observation_id, account__owner=owner)
    )
    account = item.account
    if not settings.LIVE_TRADING_ENABLED:
        raise ValidationError("اجرای Live روی سرور خاموش است.")
    if (
        account.environment != "live"
        or account.status != "connected"
        or not account.trading_enabled
        or account.permissions.get("can_trade_spot") is not True
        or account.permissions.get("can_withdraw") is not False
    ):
        raise ValidationError("حساب برای مدیریت Live ایمن و مجاز نیست.")
    policy = ExternalTradePolicy.objects.select_for_update().filter(observation=item).first()
    if policy is None:
        policy = ExternalTradePolicy(observation=item)
    elif policy.exit_order_id and policy.exit_order.state not in {"failed", "cancelled"}:
        raise ValidationError("برای این معامله قبلاً سفارش خروج ثبت شده است.")
    policy.market = data["market"]
    for name in (
        "entry_price", "remaining_amount", "stop_loss", "tp1", "tp2", "tp3",
        "trailing_enabled", "trailing_sl_enabled", "trailing_trigger",
        "trailing_distance_percent",
    ):
        setattr(policy, name, data.get(name))
    policy.effective_stop = data["stop_loss"]
    policy.trailing_active = False
    policy.high_water = None
    policy.state = ExternalTradePolicy.State.ACTIVE
    policy.exit_order = None
    policy.exit_request_key = uuid.uuid4()
    if policy.pk:
        policy.version += 1
    policy.save()
    record_audit(
        "external.management_enabled",
        user=owner,
        metadata={"observation_id": item.pk, "policy_id": policy.pk, "market_id": policy.market_id},
    )
    return policy


def _target_price(policy):
    return {1: policy.tp1, 2: policy.tp2, 3: policy.tp3}.get(policy.trailing_trigger)


def monitor_policy(policy_id):
    policy = (
        ExternalTradePolicy.objects.select_related(
            "observation__account__exchange", "market"
        ).get(pk=policy_id)
    )
    if policy.state != ExternalTradePolicy.State.ACTIVE:
        return policy.state
    account = policy.observation.account
    if (
        not settings.LIVE_TRADING_ENABLED
        or account.status != "connected"
        or not account.trading_enabled
        or account.permissions.get("can_trade_spot") is not True
        or account.permissions.get("can_withdraw") is not False
    ):
        return "safety_gate_closed"
    adapter = get_adapter(
        account.exchange.adapter_code,
        credentials=get_account_credentials(account),
        environment=account.environment,
    )
    ticker = adapter.fetch_ticker(policy.market.symbol)
    price = ticker.price
    with transaction.atomic():
        policy = ExternalTradePolicy.objects.select_for_update().select_related(
            "observation__account__exchange", "market"
        ).get(pk=policy_id)
        if policy.state != ExternalTradePolicy.State.ACTIVE:
            return policy.state
        changed = False
        if (
            policy.trailing_sl_enabled
            and price >= policy.tp1
            and policy.effective_stop < policy.entry_price
        ):
            policy.effective_stop = policy.entry_price
            changed = True
        trigger_price = _target_price(policy)
        if policy.trailing_enabled and trigger_price is None:
            policy.state = ExternalTradePolicy.State.ERROR
            policy.save(update_fields=("state", "updated_at"))
            return "invalid_trigger"
        if policy.trailing_enabled and price >= trigger_price:
            if not policy.trailing_active:
                policy.trailing_active = True
                policy.high_water = price
                changed = True
            else:
                policy.high_water = max(policy.high_water or price, price)
            derived = policy.high_water * (
                Decimal("100") - policy.trailing_distance_percent
            ) / Decimal("100")
            if derived > policy.effective_stop:
                policy.effective_stop = derived
                changed = True
        if price > policy.effective_stop:
            if changed:
                policy.version += 1
                policy.save()
            return "monitored"
        step = policy.market.price_step
        exit_price = price
        if step and step > 0:
            exit_price = (price / step).to_integral_value(rounding=ROUND_DOWN) * step
        order, created = queue_live_spot_order(
            policy.observation.account.owner,
            account,
            {
                "request_key": policy.exit_request_key,
                "market": policy.market,
                "side": "sell",
                "amount": policy.remaining_amount,
                "price": exit_price,
            },
        )
        policy.exit_order = order
        policy.state = ExternalTradePolicy.State.EXIT_SUBMITTED
        policy.version += 1
        policy.save()
        record_audit(
            "external.exit_queued",
            user=account.owner,
            metadata={"policy_id": policy.pk, "order_id": order.pk},
        )
        if created:
            transaction.on_commit(
                lambda order_id=order.pk: live_spot_order.apply_async(
                    args=[order_id], queue="orders"
                )
            )
        return "exit_submitted"


def monitor_active_external_trades():
    outcomes = {"monitored": 0, "submitted": 0, "errors": 0}
    ids = list(
        ExternalTradePolicy.objects.filter(state=ExternalTradePolicy.State.ACTIVE)
        .order_by("updated_at")
        .values_list("pk", flat=True)[:50]
    )
    for policy_id in ids:
        try:
            status = monitor_policy(policy_id)
            if status == "exit_submitted":
                outcomes["submitted"] += 1
            else:
                outcomes["monitored"] += 1
        except (AdapterError, ValidationError, ValueError, ArithmeticError, OSError, TimeoutError):
            outcomes["errors"] += 1
    return outcomes
