"""Advisory capital sizing from fresh free USDT in the selected trading wallet."""

from datetime import timedelta
from decimal import ROUND_DOWN, Decimal, InvalidOperation, localcontext

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.security import session_api_required
from apps.exchanges.models import BalanceSnapshot, ExchangeMarket, UserExchangeAccount

from .calculations import budget_wallet_scope


def positive(value, label):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number <= 0 or not -16 <= number.adjusted() <= 15:
            raise ValueError
        return number
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValidationError(f"{label} باید عدد مثبت و محدود باشد.") from error


def calculate(account, market, data):
    with localcontext() as ctx:
        ctx.prec = 60
        entry = positive(data.get("entry"), "Entry")
        stop = positive(data.get("stop"), "SL")
        risk = positive(data.get("risk_percent", "1"), "ریسک")
        leverage = positive(data.get("leverage", "1"), "اهرم")
        side = data.get("side", "long")
        if risk > 20 or side not in ("long", "short"):
            raise ValidationError("ریسک یا جهت معتبر نیست.")
        if (side == "long" and stop >= entry) or (side == "short" and stop <= entry):
            raise ValidationError("SL باید متناسب با جهت معامله در سمت زیان Entry باشد.")
        if market.quote_asset.symbol != "USDT" or market.market_type not in ("spot", "margin"):
            raise ValidationError("بازار USDT در Spot یا Margin لازم است.")
        if market.market_type == "spot" and (leverage != 1 or side != "long"):
            raise ValidationError("Spot فقط Long با اهرم ۱ است.")
        if not market.max_leverage or leverage > market.max_leverage:
            raise ValidationError("اهرم از سقف صرافی بیشتر است.")
        if market.market_type == "margin" and not account.permissions.get("can_trade_margin"):
            raise ValidationError("مجوز Margin این حساب تأیید نشده است.")
        now = timezone.now()
        balance = (
            BalanceSnapshot.objects.filter(
                exchange_account=account,
                asset=market.quote_asset,
                wallet_scope=budget_wallet_scope(account, market),
            )
            .order_by("-captured_at", "-pk")
            .first()
        )
        if not balance or not now - timedelta(minutes=15) <= balance.captured_at <= now + timedelta(
            seconds=5
        ):
            raise ValidationError("موجودی تتر آزاد این حساب تازه نیست؛ Sync را اجرا کنید.")
        available = balance.free_balance
        if available <= 0:
            raise ValidationError("تتر آزاد برای این حساب موجود نیست.")
        fee = market.taker_fee
        if fee is None or not Decimal(0) <= fee < 1:
            raise ValidationError("کارمزد بازار مشخص نیست؛ Sync را اجرا کنید.")
        budget = available * risk / 100
        fraction = abs(entry - stop) / entry
        raw_notional = budget / fraction
        cash_factor = 1 / leverage + fee
        maximum = available / cash_factor
        if market.max_amount:
            maximum = min(maximum, market.max_amount * entry)
        theoretical = min(raw_notional, maximum)
        capital = (theoretical * cash_factor).to_integral_value(rounding=ROUND_DOWN)
        quantity = capital / cash_factor / entry if capital else Decimal(0)
        if market.amount_step and market.amount_step > 0:
            quantity = (quantity / market.amount_step).to_integral_value(
                rounding=ROUND_DOWN
            ) * market.amount_step
        actual_notional = quantity * entry
        warnings = []
        if capital < 1 or (market.min_notional and actual_notional < market.min_notional):
            warnings.append("پیشنهاد از حداقل ارزش سفارش کمتر است.")
        if not market.amount_step or (market.min_amount and quantity < market.min_amount):
            warnings.append("حداقل حجم یا دقت بازار هنوز اجازه ارسال این پیشنهاد را نمی‌دهد.")
        return {
            "available": str(available),
            "balance_captured_at": balance.captured_at,
            "wallet_scope": balance.wallet_scope,
            "risk_budget": str(budget),
            "stop_distance_percent": str(fraction * 100),
            "raw_notional": str(raw_notional),
            "suggested_notional": str(theoretical),
            "suggested_capital": str(capital),
            "suggested_quantity": str(quantity),
            "estimated_entry_fee": str(actual_notional * fee),
            "estimated_stop_loss": str(quantity * abs(entry - stop)),
            "used_leverage": str(leverage),
            "max_leverage": str(market.max_leverage),
            "capped_by_available_balance": raw_notional > maximum,
            "warnings": warnings,
            "fees_in_risk_budget": False,
            "advisory_only": True,
        }


@session_api_required
@never_cache
@require_POST
def api_fix_loss(request):
    from apps.core.react_views import _body

    try:
        data = _body(request)
        account = get_object_or_404(
            UserExchangeAccount.objects.for_user(request.user),
            pk=int(data.get("account_id")),
            status__in=("connected", "restricted"),
            permissions__can_read=True,
        )
        market = get_object_or_404(
            ExchangeMarket.objects.select_related("quote_asset"),
            pk=int(data.get("market_id")),
            exchange=account.exchange,
            active=True,
        )
        return JsonResponse(calculate(account, market, data))
    except (ValidationError, InvalidOperation, ValueError, TypeError, ArithmeticError) as error:
        return JsonResponse({"error": getattr(error, "messages", [str(error)])}, status=400)
