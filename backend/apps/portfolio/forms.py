from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from apps.exchanges.models import ExchangeMarket

from .external_utils import normalized_external


class ExternalTradePolicyForm(forms.Form):
    entry_price = forms.DecimalField(label="Entry تأییدشده", max_digits=32, decimal_places=16)
    remaining_amount = forms.DecimalField(
        label="حجم باقی‌مانده", max_digits=32, decimal_places=16, min_value=Decimal("0.0000000000000001")
    )
    stop_loss = forms.DecimalField(label="SL", max_digits=32, decimal_places=16)
    tp1 = forms.DecimalField(label="TP1", max_digits=32, decimal_places=16)
    tp2 = forms.DecimalField(label="TP2", max_digits=32, decimal_places=16, required=False)
    tp3 = forms.DecimalField(label="TP3", max_digits=32, decimal_places=16, required=False)
    trailing_sl_enabled = forms.BooleanField(label="Trailing SL", required=False, initial=True)
    trailing_enabled = forms.BooleanField(label="Trailing", required=False, initial=True)
    trailing_trigger = forms.ChoiceField(
        label="شروع Trailing", choices=(("1", "TP1"), ("2", "TP2"), ("3", "TP3")), initial="1"
    )
    trailing_distance_percent = forms.IntegerField(
        label="فاصله Trailing (%)", min_value=1, max_value=99, initial=1
    )
    confirmed = forms.BooleanField(
        label="تأیید می‌کنم حجم باقی‌مانده و Entry را خودم بررسی کرده‌ام"
    )

    def __init__(self, *args, item, instance=None, **kwargs):
        self.item = item
        self.instance = instance
        initial = dict(kwargs.pop("initial", {}) or {})
        normalized = normalized_external(item)
        if instance:
            for name in (
                "entry_price", "remaining_amount", "stop_loss", "tp1", "tp2", "tp3",
                "trailing_sl_enabled", "trailing_enabled", "trailing_trigger",
                "trailing_distance_percent",
            ):
                initial[name] = getattr(instance, name)
        else:
            if normalized["entry"] is not None:
                initial["entry_price"] = normalized["entry"]
            if normalized["amount"] is not None:
                initial["remaining_amount"] = normalized["amount"]
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "input")

    def clean(self):
        data = super().clean()
        normalized = normalized_external(self.item)
        account = self.item.account
        if not normalized["manageable"]:
            raise ValidationError("این مشاهده برای واگذاری مدیریت، خرید اجراشده قابل اتکا ندارد.")
        if (
            account.environment != "live"
            or account.status != "connected"
            or not account.trading_enabled
            or account.permissions.get("can_trade_spot") is not True
            or account.permissions.get("can_withdraw") is not False
        ):
            raise ValidationError("حساب Live با Read+Spot و Withdrawal خاموش لازم است.")
        market = ExchangeMarket.objects.filter(
            exchange=account.exchange,
            symbol=normalized["symbol"],
            market_type="spot",
            active=True,
        ).first()
        if not market:
            raise ValidationError("بازار Spot فعال این مشاهده در کاتالوگ صرافی پیدا نشد.")
        required = [data.get(k) for k in ("entry_price", "remaining_amount", "stop_loss", "tp1")]
        if any(value is None or value <= 0 for value in required):
            return data
        entry = data["entry_price"]
        targets = [data["tp1"]]
        if data.get("tp2") is not None:
            targets.append(data["tp2"])
        if data.get("tp3") is not None:
            if data.get("tp2") is None:
                self.add_error("tp3", "TP3 بدون TP2 معتبر نیست.")
            targets.append(data["tp3"])
        if not (data["stop_loss"] < entry and all(tp > entry for tp in targets)):
            raise ValidationError("برای Spot Long باید SL پایین‌تر و TPها بالاتر از Entry باشند.")
        if targets != sorted(set(targets)):
            raise ValidationError("TPها باید صعودی و غیرتکراری باشند.")
        trigger = int(data.get("trailing_trigger") or 1)
        if data.get("trailing_enabled") and trigger > len(targets):
            self.add_error("trailing_trigger", "TP شروع Trailing در این معامله تعریف نشده است.")
        amount = data["remaining_amount"]
        if market.amount_step and amount % market.amount_step:
            self.add_error("remaining_amount", "حجم با Lot Step صرافی سازگار نیست.")
        if market.min_amount and amount < market.min_amount:
            self.add_error("remaining_amount", "حجم از حداقل بازار کمتر است.")
        latest = account.balance_snapshots.filter(asset=market.base_asset).order_by("-captured_at").first()
        if not latest or latest.free_balance < amount:
            self.add_error(
                "remaining_amount",
                "موجودی آزاد تازه برای این حجم کافی نیست؛ ابتدا حساب را همگام کنید.",
            )
        data["market"] = market
        data["trailing_trigger"] = trigger
        return data
