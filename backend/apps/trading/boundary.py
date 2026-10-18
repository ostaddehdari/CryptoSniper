"""One execution boundary shared by risk, state, executor and exit engines."""

from django.conf import settings
from django.core.exceptions import ValidationError


def require_paper_simulator(order):
    """Fail closed before any provider transport can be selected."""

    account = order.account
    trade = order.trade
    if settings.TRADING_MODE != "paper" or settings.LIVE_TRADING_ENABLED:
        raise ValidationError("این build فقط با مرز Paper ایمن اجرا می‌شود.")
    if trade.mode != "paper" or account.environment != "paper":
        raise ValidationError("حساب و معامله باید هر دو Paper باشند.")
    if account.exchange.adapter_code != "simulator":
        raise ValidationError("Paper فقط از Simulator داخلی استفاده می‌کند.")
    if not account.credentials_encrypted:
        raise ValidationError("هویت Simulator این حساب ابطال شده است.")
    return account
