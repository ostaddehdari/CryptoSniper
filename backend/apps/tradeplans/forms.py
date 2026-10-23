import uuid

from django import forms

from apps.exchanges.models import ExchangeMarket, UserExchangeAccount
from apps.signals.models import Signal


class ManualTradeForm(forms.Form):
    account = forms.ModelChoiceField(
        label="حساب صرافی", queryset=UserExchangeAccount.objects.none()
    )
    market = forms.ModelChoiceField(label="ارز و جفت‌ارز", queryset=ExchangeMarket.objects.none())
    source = forms.ChoiceField(label="منبع", choices=[("manual", "ورود دستی")])
    side = forms.ChoiceField(
        label="جهت معامله", choices=[("long", "Long / خرید"), ("short", "Short / فروش")]
    )
    entry_price = forms.DecimalField(
        label="قیمت ورود", max_digits=32, decimal_places=16, min_value=0.0000000000000001
    )
    tp1 = forms.DecimalField(
        label="TP1", max_digits=32, decimal_places=16, min_value=0.0000000000000001
    )
    tp2 = forms.DecimalField(
        label="TP2", max_digits=32, decimal_places=16, min_value=0.0000000000000001, required=False
    )
    tp3 = forms.DecimalField(
        label="TP3", max_digits=32, decimal_places=16, min_value=0.0000000000000001, required=False
    )
    stop_loss = forms.DecimalField(
        label="حد ضرر (SL)", max_digits=32, decimal_places=16, min_value=0.0000000000000001
    )
    capital = forms.DecimalField(
        label="مبلغ سرمایه (به ارز Quote)",
        max_digits=32,
        decimal_places=16,
        min_value=0.0000000000000001,
    )
    leverage = forms.DecimalField(
        label="اهرم", max_digits=10, decimal_places=4, min_value=1, initial=1
    )
    trailing_sl = forms.BooleanField(label="Trailing SL", required=False)
    percentage_trailing = forms.BooleanField(label="Trailing", required=False)
    percentage_trigger = forms.ChoiceField(
        label="شروع Trailing",
        choices=(("tp1", "TP1"), ("tp2", "TP2"), ("tp3", "TP3")),
        initial="tp1",
    )
    trailing_distance = forms.DecimalField(
        label="فاصله trailing (%)",
        max_digits=8,
        decimal_places=4,
        min_value=0.001,
        max_value=99,
        initial=1,
    )
    origin_signal = forms.ModelChoiceField(
        queryset=Signal.objects.none(), required=False, widget=forms.HiddenInput
    )
    client_token = forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self, owner, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["origin_signal"].queryset = Signal.objects.filter(
            owner=owner, status=Signal.Status.APPROVED
        )
        self.fields["account"].queryset = (
            UserExchangeAccount.objects.for_user(owner)
            .filter(status__in=("connected", "restricted"), permissions__can_read=True)
            .select_related("exchange")
        )
        self.fields["market"].queryset = ExchangeMarket.objects.filter(
            exchange_id__in=self.fields["account"].queryset.values("exchange_id"), active=True
        ).select_related("exchange")
        for key, field in self.fields.items():
            if key not in {"client_token", "origin_signal"}:
                field.widget.attrs.setdefault("class", "input")
            if key in {
                "entry_price",
                "tp1",
                "tp2",
                "tp3",
                "stop_loss",
                "capital",
                "leverage",
                "trailing_distance",
            }:
                field.widget.attrs.update({"inputmode": "decimal", "dir": "ltr"})
        if not self.is_bound:
            self.initial.setdefault("client_token", uuid.uuid4())

    def clean(self):
        data = super().clean()
        account, market = data.get("account"), data.get("market")
        if account and market:
            if account.exchange_id != market.exchange_id:
                self.add_error("market", "بازار باید متعلق به همان حساب صرافی باشد.")
            if market.market_type == "margin" and not account.permissions.get("can_trade_margin"):
                self.add_error("market", "مجوز Margin این حساب تأیید نشده است.")
            if market.market_type == "spot" and data.get("side") != "long":
                self.add_error("side", "Spot فقط خرید Long را پشتیبانی می‌کند.")
        origin = data.get("origin_signal")
        if origin:
            if origin.status != Signal.Status.APPROVED:
                self.add_error("origin_signal", "سیگنال باید ابتدا تأیید شده باشد.")
            if (
                account
                and market
                and (origin.exchange_account_id != account.pk or origin.market_id != market.pk)
            ):
                self.add_error("origin_signal", "حساب و بازار باید با سیگنال تأییدشده برابر باشند.")
        targets = (data.get("tp1"), data.get("tp2"), data.get("tp3"))
        if targets[2] and not targets[1]:
            self.add_error("tp3", "TP3 بدون TP2 معتبر نیست.")
        return data
