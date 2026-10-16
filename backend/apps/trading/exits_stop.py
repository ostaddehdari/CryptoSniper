"""Monotonic manual stop adjustments with audit and optimistic version control (Paper)."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.audit import record_audit

from .exits_plan import ensure_exits
from .models import Trade, TradeEvent, TradeProtection, TradeTarget


@transaction.atomic
def adjust_stop(owner, trade_id, *, version, mode, price=None, reason=""):
    trade = Trade.objects.select_for_update().get(pk=trade_id, owner=owner)
    if trade.mode != "paper" or trade.state not in {Trade.State.OPEN, Trade.State.PARTIAL}:
        raise ValidationError("تنها Stop یک Position باز Paper قابل تغییر است.")
    protection = TradeProtection.objects.select_for_update().filter(trade=trade).first()
    if protection is None:
        protection, _ = ensure_exits(trade.pk)
    if protection.version != version:
        raise ValidationError("نسخه Stop قدیمی شده است؛ صفحه را به‌روز کنید.")
    if len(reason.strip()) < 3 or len(reason) > 500:
        raise ValidationError("دلیل تغییر Stop باید حداقل سه و حداکثر پانصد نویسه باشد.")
    if mode == "breakeven":
        candidate = trade.entry_price
    elif mode == "previous_tp":
        fulfilled = list(TradeTarget.objects.filter(
            trade=trade, state=TradeTarget.State.FILLED
        ).order_by("position"))
        if not fulfilled:
            raise ValidationError("برای انتقال Stop به هدف قبلی، ابتدا TP باید تکمیل شود.")
        candidate = trade.entry_price if len(fulfilled) == 1 else fulfilled[-2].price
    elif mode == "manual":
        try:
            candidate = Decimal(str(price))
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise ValidationError("Stop جدید عدد معتبر ندارد.") from exc
    else:
        raise ValidationError("روش تغییر Stop ناشناخته است.")
    if not candidate.is_finite() or candidate <= 0:
        raise ValidationError("Stop جدید باید مثبت و محدود باشد.")
    step = trade.market.price_step
    if step is None or step <= 0 or candidate % step:
        raise ValidationError("Stop جدید باید با Tick Size مطابقت داشته باشد.")
    if candidate < protection.effective_stop:
        raise ValidationError("Stop نباید ضعیف‌تر شود.")
    if protection.last_price and candidate >= protection.last_price:
        raise ValidationError("Stop جدید باید پایین‌تر از آخرین قیمت معتبر بازار باشد.")
    if candidate == protection.effective_stop:
        return protection, False
    previous = protection.effective_stop
    protection.effective_stop = candidate
    protection.version += 1
    protection.save(update_fields=("effective_stop", "version", "updated_at"))
    TradeEvent.objects.create(trade=trade, event_type="MANUAL_STOP_MOVED",
                              payload={"from":str(previous), "to":str(candidate),
                                       "reason":reason.strip(), "mode":mode})
    record_audit("paper_stop.adjusted", user=owner,
                 metadata={"trade_id":trade.pk, "version":protection.version})
    return protection, True
