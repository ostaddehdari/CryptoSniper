"""Deterministic Decimal-only manual trade preview; never sends exchange orders."""

from datetime import timedelta
from decimal import ROUND_DOWN, Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.exchanges.models import BalanceSnapshot

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def text(value):
    return format(value, "f")


def _market_multiple(price, step):
    if not step or step <= ZERO:
        raise ValidationError("Precision قیمت بازار مشخص نیست؛ ابتدا همگام‌سازی کنید.")
    if (price / step) != (price / step).to_integral_value():
        raise ValidationError("قیمت با Tick Size صرافی سازگار نیست.")


def _targets(data):
    values = [data["tp1"]]
    for key in ("tp2", "tp3"):
        if data.get(key) is not None:
            values.append(data[key])
    if not (1 <= len(values) <= 3):
        raise ValidationError("بین یک تا سه هدف سود لازم است.")
    return values


def build_preview(data, now=None):
    """Data are Django-form-cleaned Decimals + owner-scoped account and market objects."""
    now = now or timezone.now()
    market, account = data["market"], data["account"]
    if market.exchange_id != account.exchange_id:
        raise ValidationError("حساب صرافی و بازار هم‌خوان نیستند.")
    if not market.active or account.status not in {"connected", "restricted"}:
        raise ValidationError("بازار یا اتصال صرافی فعال نیست.")
    if account.permissions.get("can_read") is not True:
        raise ValidationError("دسترسی خواندن موجودی تأیید نشده است.")
    side = data["side"]
    if side not in {"long", "short"}:
        raise ValidationError("جهت معامله نامعتبر است.")
    if market.market_type == "spot" and side != "long":
        raise ValidationError("Spot فقط Long است.")
    if market.market_type == "margin" and not account.permissions.get("can_trade_margin"):
        raise ValidationError("مجوز Margin تأیید نشده است.")
    entry, sl = data["entry_price"], data["stop_loss"]
    targets = _targets(data)
    leverage = data["leverage"]
    capital = data["capital"]
    if leverage < Decimal("1") or capital <= ZERO or entry <= ZERO or sl <= ZERO:
        raise ValidationError("سرمایه، ورود، حد ضرر و اهرم باید مثبت باشند.")
    if market.market_type == "spot" and leverage != Decimal("1"):
        raise ValidationError("اهرم Spot باید ۱ باشد.")
    if not market.max_leverage or leverage > market.max_leverage:
        raise ValidationError("اهرم از سقف گزارش‌شده صرافی بالاتر است.")
    if side == "long":
        if not (sl < entry and all(tp > entry for tp in targets)):
            raise ValidationError("برای Long باید SL پایین‌تر و TPها بالاتر از ورود باشند.")
        if targets != sorted(set(targets)):
            raise ValidationError("TPهای Long باید صعودی و غیرتکراری باشند.")
    else:
        if not (sl > entry and all(tp < entry for tp in targets)):
            raise ValidationError("برای Short باید SL بالاتر و TPها پایین‌تر از ورود باشند.")
        if targets != sorted(set(targets), reverse=True):
            raise ValidationError("TPهای Short باید نزولی و غیرتکراری باشند.")
    for price in [entry, sl, *targets]:
        _market_multiple(price, market.price_step)
    if not market.amount_step or market.amount_step <= ZERO:
        raise ValidationError("Lot Step بازار نامعلوم است.")
    fee_known = market.taker_fee is not None and ZERO <= market.taker_fee < Decimal("1")
    fee_rate = market.taker_fee if fee_known else ZERO
    # capital is collateral/cash to allocate including estimated entry fee.
    # Spot: notional+fee <=capital. Margin: notional/leverage+fee <=capital.
    effective_notional = capital / (Decimal("1") / leverage + fee_rate)
    raw_quantity = effective_notional / entry
    quantity = (raw_quantity / market.amount_step).to_integral_value(rounding=ROUND_DOWN)
    quantity *= market.amount_step
    if quantity <= ZERO or (market.min_amount and quantity < market.min_amount):
        raise ValidationError("سرمایه با حداقل حجم سفارش یا Lot Step سازگار نیست.")
    if market.max_amount and quantity > market.max_amount:
        raise ValidationError("مقدار محاسبه‌شده از سقف بازار بیشتر است.")
    notional = quantity * entry
    if market.min_notional and notional < market.min_notional:
        raise ValidationError("ارزش سفارش کمتر از Min Notional گزارش‌شده صرافی است.")
    entry_fee = notional * fee_rate
    exit_fee = notional * fee_rate  # indicative: actual exit price/fee will differ
    required_cash = notional / leverage + entry_fee
    if required_cash > capital:
        raise ValidationError("سرمایه اختصاص‌یافته برای کارمزد و حجم کافی نیست.")
    balances = BalanceSnapshot.objects.filter(
        exchange_account=account, asset=market.quote_asset
    ).order_by("-captured_at")
    latest = balances.first()
    if not latest or latest.captured_at < now - timedelta(minutes=15):
        raise ValidationError("موجودی Quote تازه نیست؛ ابتدا همگام‌سازی حساب را انجام دهید.")
    if latest.free_balance < required_cash:
        raise ValidationError("موجودی آزاد Quote برای سرمایه انتخاب‌شده کافی نیست.")
    percentage = (
        [Decimal("100")]
        if len(targets) == 1
        else (
            [Decimal("10"), Decimal("90")]
            if len(targets) == 2
            else [Decimal("10"), Decimal("10"), Decimal("80")]
        )
    )
    trailing_trigger = str(data.get("percentage_trigger", "tp1"))
    if trailing_trigger not in {"tp1", "tp2", "tp3"}:
        raise ValidationError("شروع Trailing باید TP1، TP2 یا TP3 باشد.")
    trigger_index = {"tp1": 0, "tp2": 1, "tp3": 2}[trailing_trigger]
    if data.get("percentage_trailing") and trigger_index >= len(targets):
        raise ValidationError("Trigger انتخاب‌شده باید TP متناظر در معامله داشته باشد.")
    trailing_distance = data.get("trailing_distance", Decimal("1"))
    if data.get("percentage_trailing") and not (ZERO < trailing_distance < HUNDRED):
        raise ValidationError("فاصله Percentage Trailing باید بین صفر و صد باشد.")
    if trailing_distance is None:
        trailing_distance = Decimal("1")
    tp_info = [
        {
            "price": text(tp),
            "share_percent": text(percentage[i]),
            "distance_percent": text(abs((tp - entry) / entry) * HUNDRED),
        }
        for i, tp in enumerate(targets)
    ]
    risk_fraction = abs((sl - entry) / entry) * HUNDRED
    return {
        "schema": "cryptosniper.tradeplan.preview.v1",
        "execution_enabled": False,
        "market_id": market.pk,
        "market_symbol": market.symbol,
        "market_type": market.market_type,
        "exchange": market.exchange.code,
        "account_id": account.pk,
        "direction": side,
        "source": "manual",
        "entry_price": text(entry),
        "stop_loss": text(sl),
        "stop_distance_percent": text(risk_fraction),
        "targets": tp_info,
        "capital": text(capital),
        "quantity": text(quantity),
        "notional": text(notional),
        "leverage": text(leverage),
        "estimated_entry_fee": text(entry_fee),
        "indicative_exit_fee_at_entry": text(exit_fee),
        "estimated_collateral_and_entry_fee": text(required_cash),
        "quote_free_balance": text(latest.free_balance),
        "quote_asset": market.quote_asset.symbol,
        "fees_are_estimates": fee_known,
        "fee_rate_known": fee_known,
        "min_notional_known": market.min_notional is not None,
        "trailing_sl": bool(data.get("trailing_sl")),
        "percentage_trailing": bool(data.get("percentage_trailing")),
        "percentage_trigger": trailing_trigger,
        "trailing_distance_percent": text(trailing_distance),
        "exit_policy": (
            f"percentage_trailing_after_{trailing_trigger}"
            if data.get("percentage_trailing")
            else "scheduled_targets"
        ),
        "calculated_at": now.isoformat(),
        "market_metadata_synced_at": market.synced_at.isoformat() if market.synced_at else None,
        "balance_captured_at": latest.captured_at.isoformat(),
    }
