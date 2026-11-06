"""Advisory capital sizing from fresh free USDT in the selected trading wallet."""

from datetime import timedelta
from decimal import ROUND_DOWN, Decimal, InvalidOperation, localcontext

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.security import session_api_required
from apps.exchanges.adapters import AdapterError, get_adapter
from apps.exchanges.models import BalanceSnapshot, ExchangeMarket, UserExchangeAccount
from apps.exchanges.security import get_account_credentials

from .calculations import budget_wallet_scope

BALANCE_FRESH_SECONDS = 30


def positive(value, label):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number <= 0 or not -16 <= number.adjusted() <= 15:
            raise ValueError
        return number
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValidationError(f"{label} باید عدد مثبت و محدود باشد.") from error


def _latest_balance(account, market):
    return (
        BalanceSnapshot.objects.filter(
            exchange_account=account,
            asset=market.quote_asset,
            wallet_scope=budget_wallet_scope(account, market),
        )
        .order_by("-captured_at", "-pk")
        .first()
    )


def ensure_fresh_balance(account, market):
    now = timezone.now()
    balance = _latest_balance(account, market)
    if balance and now - timedelta(
        seconds=BALANCE_FRESH_SECONDS
    ) <= balance.captured_at <= now + timedelta(seconds=5):
        return balance
    lock_key = (
        f"tradeplans:fixloss-balance:{account.pk}:{market.quote_asset_id}:"
        f"{budget_wallet_scope(account, market)}"
    )
    if not cache.add(lock_key, "1", timeout=12):
        balance = _latest_balance(account, market)
        if balance and now - timedelta(
            seconds=BALANCE_FRESH_SECONDS
        ) <= balance.captured_at <= now + timedelta(seconds=5):
            return balance
        raise ValidationError("دریافت تتر آزاد در حال انجام است؛ چند لحظه دیگر تلاش کنید.")
    try:
        credentials = get_account_credentials(account) if account.credentials_encrypted else {}
        adapter = get_adapter(
            account.exchange.adapter_code,
            credentials=credentials,
            environment=account.environment,
        )
        matches = [
            item
            for item in adapter.fetch_balance()
            if item.asset.upper() == market.quote_asset.symbol.upper()
        ]
        if len(matches) != 1:
            raise ValidationError("موجودی تتر آزاد این کیف پول در پاسخ صرافی مشخص نیست.")
        item = matches[0]
        if any(
            not value.is_finite() or value < 0 for value in (item.free, item.locked, item.total)
        ):
            raise ValidationError("موجودی تتر آزاد صرافی معتبر نیست.")
        return BalanceSnapshot.objects.create(
            exchange_account=account,
            asset=market.quote_asset,
            wallet_scope=budget_wallet_scope(account, market),
            free_balance=item.free,
            locked_balance=item.locked,
            total_balance=item.total,
            captured_at=now,
        )
    except (AdapterError, ImproperlyConfigured, ValueError, TypeError) as error:
        raise ValidationError(
            "تتر آزاد لحظه‌ای از صرافی دریافت نشد؛ اتصال حساب را بررسی یا Sync کنید."
        ) from error
    finally:
        cache.delete(lock_key)


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
        balance = _latest_balance(account, market)
        if not balance or not now - timedelta(
            seconds=BALANCE_FRESH_SECONDS
        ) <= balance.captured_at <= now + timedelta(seconds=5):
            raise ValidationError("موجودی تتر آزاد این حساب تازه نیست؛ Sync را اجرا کنید.")
        available = balance.free_balance
        if available <= 0:
            raise ValidationError("تتر آزاد برای این حساب موجود نیست.")
        fee = market.taker_fee
        if fee is None or not Decimal(0) <= fee < 1:
            raise ValidationError("کارمزد بازار مشخص نیست؛ Sync را اجرا کنید.")
        budget = available * risk / 100
        price_loss_fraction = abs(entry - stop) / entry
        fee_loss_fraction = fee + (stop / entry) * fee
        risk_fraction = price_loss_fraction + fee_loss_fraction
        raw_notional = budget / risk_fraction
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
        estimated_entry_fee = actual_notional * fee
        estimated_exit_fee = quantity * stop * fee
        estimated_price_loss = quantity * abs(entry - stop)
        estimated_total_risk = estimated_price_loss + estimated_entry_fee + estimated_exit_fee
        warnings = []
        if capital < 1 or (market.min_notional and actual_notional < market.min_notional):
            warnings.append("پیشنهاد از حداقل ارزش سفارش کمتر است.")
        if not market.amount_step or (market.min_amount and quantity < market.min_amount):
            warnings.append("حداقل حجم یا دقت بازار هنوز اجازه ارسال این پیشنهاد را نمی‌دهد.")
        return {
            "available": str(available),
            "balance_captured_at": balance.captured_at,
            "balance_age_seconds": max(0, int((now - balance.captured_at).total_seconds())),
            "wallet_scope": balance.wallet_scope,
            "risk_budget": str(budget),
            "stop_distance_percent": str(price_loss_fraction * 100),
            "raw_notional": str(raw_notional),
            "suggested_notional": str(theoretical),
            "suggested_capital": str(capital),
            "suggested_quantity": str(quantity),
            "estimated_entry_fee": str(estimated_entry_fee),
            "estimated_exit_fee_at_stop": str(estimated_exit_fee),
            "estimated_stop_loss": str(estimated_price_loss),
            "estimated_total_risk": str(estimated_total_risk),
            "used_leverage": str(leverage),
            "max_leverage": str(market.max_leverage),
            "capped_by_available_balance": raw_notional > maximum,
            "warnings": warnings,
            "fees_in_risk_budget": True,
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
            UserExchangeAccount.objects.for_user(request.user).select_related("exchange"),
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
        ensure_fresh_balance(account, market)
        return JsonResponse(calculate(account, market, data))
    except (ValidationError, InvalidOperation, ValueError, TypeError, ArithmeticError) as error:
        return JsonResponse({"error": getattr(error, "messages", [str(error)])}, status=400)
