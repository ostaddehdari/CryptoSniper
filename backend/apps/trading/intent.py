"""Stage08 atomic Paper intents. All irreversible decisions stay in PostgreSQL."""
import hashlib
import json
import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.exchanges.models import BalanceSnapshot, UserExchangeAccount
from apps.tradeplans.models import TradePlan

from .models import CapitalReservation, ExecutionOutbox, Order, PaperRiskPolicy, Trade, TradeEvent


def _d(value):
    try:
        val = Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError) as error:
        raise ValidationError("مبلغ یا حجم معتبر نیست.") from error
    if not val.is_finite() or val <= 0:
        raise ValidationError("مبلغ یا حجم باید مثبت و محدود باشد.")
    return val


def _hash(plan):
    blob = json.dumps(plan.approved_snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


@transaction.atomic
def queue_paper_trade(owner, plan_id, *, request_key):
    """Plan owner, account lock, quote reservation, order/outbox are atomic."""
    if not isinstance(request_key, uuid.UUID):
        raise ValidationError("شناسه یکتای درخواست UUID معتبر نیست.")
    plan = TradePlan.objects.select_related(
        "exchange_account", "market", "market__quote_asset"
    ).get(owner=owner, pk=plan_id, status=TradePlan.Status.READY)
    account = UserExchangeAccount.objects.select_for_update().select_related(
        "exchange"
    ).get(pk=plan.exchange_account_id, owner=owner)
    digest = _hash(plan)
    previous = Trade.objects.filter(owner=owner, request_key=request_key).first()
    if previous:
        if previous.request_hash != digest or previous.plan_id != plan.pk:
            raise ValidationError("کلید تکراری برای برنامه دیگری استفاده شده است.")
        return previous, False
    if account.environment != "paper" or account.exchange.adapter_code != "simulator":
        raise ValidationError("این مرحله فقط برای حساب شبیه‌ساز Paper مجاز است.")
    if account.status != "connected" or not account.permissions.get("can_read"):
        raise ValidationError("حساب Paper فعال و تأییدشده نیست.")
    market = plan.market
    if market.market_type != "spot" or plan.side != "long" or not market.active:
        raise ValidationError("در Stage08 فقط Spot Long آزمایشی مجاز است.")
    if plan.leverage != Decimal("1"):
        raise ValidationError("اهرم باید دقیقاً ۱ باشد.")
    snap = plan.approved_snapshot
    if snap.get("execution_enabled") is not False or snap.get("market_id") != market.pk:
        raise ValidationError("Snapshot معتبر نیست.")
    quantity = _d(snap.get("quantity"))
    capital = _d(snap.get("estimated_collateral_and_entry_fee"))
    entry_price = _d(snap.get("entry_price"))
    if quantity * entry_price < (market.min_notional or Decimal("1e50")):
        raise ValidationError("حداقل ارزش سفارش رعایت نشده است.")
    policy, _ = PaperRiskPolicy.objects.get_or_create(owner=owner)
    if Trade.objects.filter(account=account, state__in=(
        Trade.State.QUEUED, Trade.State.SUBMITTING, Trade.State.PARTIAL,
        Trade.State.OPEN, Trade.State.UNCERTAIN
    )).count() >= policy.max_active_trades:
        raise ValidationError("سقف تعداد معاملات فعال Paper تکمیل شده است.")
    if capital > policy.max_capital_per_trade:
        raise ValidationError("مبلغ معامله از سقف سرمایه Paper بیشتر است.")
    latest = BalanceSnapshot.objects.filter(
        exchange_account=account, asset=market.quote_asset
    ).order_by("-captured_at").first()
    if latest is None or latest.captured_at < timezone.now() - timedelta(minutes=15):
        raise ValidationError("موجودی جدید و معتبر لازم است.")
    committed = CapitalReservation.objects.filter(
        account=account, quote_asset=market.quote_asset, active=True
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    # Includes spent allocations until explicit paper reset; no false double spending.
    if committed + capital > policy.max_total_allocated:
        raise ValidationError("سقف سرمایه تخصیص‌یافته در حساب Paper تکمیل شده است.")
    if latest.free_balance - committed < capital:
        raise ValidationError("موجودی آزاد بعد از رزروهای هم‌زمان کافی نیست.")
    trade = Trade.objects.create(
        owner=owner, account=account, market=market, plan=plan,
        request_key=request_key, request_hash=digest,
        quantity=quantity, entry_price=entry_price,
        capital_reserved=capital, snapshot=dict(snap), side="buy",
    )
    CapitalReservation.objects.create(
        trade=trade, account=account, quote_asset=market.quote_asset,
        amount=capital,
    )
    order = Order.objects.create(
        trade=trade, account=account, client_order_id=f"cs-paper-{trade.pk}",
        quantity=quantity, price=entry_price,
    )
    ExecutionOutbox.objects.create(order=order)
    TradeEvent.objects.create(trade=trade, event_type="QUEUED",
                              payload={"mode": "paper", "order_id": order.pk})
    return trade, True
