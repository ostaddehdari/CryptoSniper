from decimal import Decimal

from django import forms

from apps.exchanges.models import ExchangeMarket, UserExchangeAccount

from .models import SignalSource


class ReceiveForm(forms.Form):
    method = forms.ChoiceField(
        label="روش ورود",
        choices=[
            (SignalSource.Method.MANUAL, "ورود دستی"),
            (SignalSource.Method.SMART_PASTE, "Smart Paste (بدون تحلیل خودکار تا S07)"),
        ],
    )
    text = forms.CharField(
        label="متن اصلی سیگنال",
        max_length=40000,
        widget=forms.Textarea(attrs={"rows": 8, "placeholder": "متن اصلی بدون تغییر ذخیره می‌شود."}),
    )


class ReviewForm(forms.Form):
    account_id = forms.ModelChoiceField(
        label="حساب صرافی", queryset=UserExchangeAccount.objects.none()
    )
    market_id = forms.ModelChoiceField(label="بازار", queryset=ExchangeMarket.objects.none())
    side = forms.ChoiceField(label="جهت", choices=(("long", "Long"), ("short", "Short")))
    entry_price = forms.DecimalField(
        label="Entry", max_digits=32, decimal_places=16, min_value=Decimal("0.0000000000000001")
    )
    stop_loss = forms.DecimalField(
        label="Stop Loss", max_digits=32, decimal_places=16, min_value=Decimal("0.0000000000000001")
    )
    tp1 = forms.DecimalField(
        label="TP1", max_digits=32, decimal_places=16, min_value=Decimal("0.0000000000000001")
    )
    tp2 = forms.DecimalField(
        label="TP2",
        required=False,
        max_digits=32,
        decimal_places=16,
        min_value=Decimal("0.0000000000000001"),
    )
    tp3 = forms.DecimalField(
        label="TP3",
        required=False,
        max_digits=32,
        decimal_places=16,
        min_value=Decimal("0.0000000000000001"),
    )
    revision = forms.IntegerField(widget=forms.HiddenInput, min_value=1)
    reason = forms.CharField(label="دلیل ویرایش", max_length=500, min_length=3)

    def __init__(self, owner, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account_id"].queryset = UserExchangeAccount.objects.for_user(owner).filter(
            status__in=("connected", "restricted")
        )
        self.fields["market_id"].queryset = ExchangeMarket.objects.filter(
            active=True,
            exchange_id__in=self.fields["account_id"].queryset.values_list(
                "exchange_id", flat=True
            ),
        )
        for name, field in self.fields.items():
            if name != "revision":
                field.widget.attrs.setdefault("class", "input")

    def clean(self):
        data = super().clean()
        account, market = data.get("account_id"), data.get("market_id")
        if account and market and account.exchange_id != market.exchange_id:
            self.add_error("market_id", "بازار متعلق به اتصال دیگری است.")
        if data.get("tp3") is not None and data.get("tp2") is None:
            self.add_error("tp3", "TP3 بدون TP2 معتبر نیست.")
        return data

    def structured(self):
        data = self.cleaned_data
        return {
            "account_id": data["account_id"].pk,
            "market_id": data["market_id"].pk,
            "side": data["side"],
            "entry_price": data["entry_price"],
            "stop_loss": data["stop_loss"],
            "targets": [
                {"price": data[key]} for key in ("tp1", "tp2", "tp3") if data.get(key) is not None
            ],
        }
