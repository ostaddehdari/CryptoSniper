"""Monotonic Paper trailing policy, version locking, and event audit."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.audit import record_audit

from .models import Order, Trade, TradeEvent, TradeProtection, TradeTarget


@transaction.atomic
def configure_trailing(owner, trade_id, *, version, step_enabled, percentage_enabled,
                       distance_percent, reason):
    trade = Trade.objects.select_for_update().select_related(
        "account", "account__exchange"
    ).get(owner=owner, pk=trade_id)
    if trade.state not in {Trade.State.OPEN, Trade.State.PARTIAL}:
        raise ValidationError("قواعد trailing فقط روی Paper Position باز قابل تغییرند.")
    if (trade.account.environment != "paper"
            or trade.account.exchange.adapter_code != "simulator"):
        raise ValidationError("تغییر قواعد در حساب واقعی ممنوع است.")
    protection = TradeProtection.objects.select_for_update().get(trade=trade)
    if protection.version != int(version):
        raise ValidationError("قواعد در تب دیگری تغییر کرده‌اند؛ صفحه را تازه کنید.")
    if len(reason.strip()) < 3 or len(reason) > 500:
        raise ValidationError("دلیل اصلاح باید بین سه تا پانصد نویسه باشد.")
    try:
        distance = Decimal(str(distance_percent))
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise ValidationError("فاصله trailing معتبر نیست.") from exc
    if not distance.is_finite() or not Decimal("0") < distance < Decimal("100"):
        raise ValidationError("فاصله trailing باید بین صفر و صد باشد.")
    if protection.percentage_active and not percentage_enabled:
        raise ValidationError("Percentage پس از فعال‌سازی بدون بستن معامله خاموش نمی‌شود.")
    if percentage_enabled and not protection.percentage_enabled:
        # TP exits in this Paper implementation are ledger intents, not native
        # orders. Fail closed if *any* external exit order is unexpectedly present.
        unexpected = Order.objects.filter(
            trade=trade,
            client_order_id__startswith=f"cs-paper-exit-{trade.pk}",
        ).exclude(state=Order.State.CANCELLED)
        if unexpected.exists():
            protection.coverage = TradeProtection.Coverage.CANCELLING
            protection.save(update_fields=("coverage", "updated_at"))
            raise ValidationError("لغو سفارش خروج هنوز تأیید نشده؛ حالت Percentage فعال نشد.")
        cancelled = TradeTarget.objects.filter(trade=trade, state__in=[
            TradeTarget.State.WAITING, TradeTarget.State.PARTIAL,
        ]).update(state=TradeTarget.State.CANCELLED)
        TradeEvent.objects.create(
            trade=trade, event_type="PAPER_TARGETS_CANCELLED",
            payload={"count":cancelled, "reason":"switch_to_percentage",
                     "native_orders":0, "reconciled":True},
        )
    elif protection.percentage_enabled and not percentage_enabled:
        # Only possible before activation. Filled targets are not revived.
        TradeTarget.objects.filter(trade=trade, state=TradeTarget.State.CANCELLED).update(
            state=TradeTarget.State.WAITING
        )
    old = {"step":protection.step_enabled,
           "percentage":protection.percentage_enabled,
           "distance":str(protection.distance_percent)}
    protection.step_enabled = bool(step_enabled)
    protection.percentage_enabled = bool(percentage_enabled)
    protection.distance_percent = distance
    protection.version += 1
    protection.save(update_fields=("step_enabled", "percentage_enabled",
                                   "distance_percent", "version", "updated_at"))
    TradeEvent.objects.create(
        trade=trade, event_type="TRAILING_RULE_UPDATED",
        payload={"from":old, "to":{"step":protection.step_enabled,
                                    "percentage":protection.percentage_enabled,
                                    "distance":str(distance)},
                 "reason":reason.strip(), "stop":str(protection.effective_stop)}
    )
    record_audit("paper.trailing.updated", user=owner,
                 metadata={"trade_id":trade.pk, "version":protection.version})
    return protection
