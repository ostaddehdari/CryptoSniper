from django import forms

from apps.marketdata.search import eligible_markets
from apps.trading.models import Trade

from .engine import PROXIMITY, TRADE_ONLY
from .models import PriceAlert


class AlertForm(forms.ModelForm):
    version = forms.IntegerField(min_value=1, initial=1, widget=forms.HiddenInput)

    class Meta:
        model = PriceAlert
        fields = (
            "title",
            "market",
            "trade",
            "kind",
            "direction",
            "threshold",
            "repeat",
            "hysteresis",
            "cooldown_seconds",
            "enabled",
        )
        labels = {
            "title": "عنوان هشدار",
            "market": "بازار",
            "trade": "معامله Paper (اختیاری)",
            "kind": "نوع هشدار",
            "direction": "جهت عبور",
            "threshold": "آستانه: قیمت یا درصد",
            "repeat": "تکرار پس از خروج از محدوده و عبور مجدد",
            "hysteresis": "حاشیه بازآماده‌سازی (درصد قیمت / واحد درصد)",
            "cooldown_seconds": "حداقل فاصله اعلان‌ها (ثانیه)",
            "enabled": "فعال",
        }

    def __init__(self, owner, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["market"].queryset = eligible_markets(owner).filter(market_type="spot")
        self.fields["trade"].queryset = Trade.objects.filter(
            owner=owner,
            mode="paper",
            state__in=["open", "partially_filled"],
            account__exchange__adapter_code="simulator",
        )
        self.fields["trade"].required = False
        if self.instance.pk:
            self.fields["version"].initial = self.instance.version
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.CheckboxInput, forms.HiddenInput)):
                field.widget.attrs["class"] = "input"

    def clean(self):
        values = super().clean()
        trade, market, kind, threshold = (
            values.get(k) for k in ("trade", "market", "kind", "threshold")
        )
        if trade and market and trade.market_id != market.pk:
            self.add_error("trade", "بازار معامله و هشدار باید یکسان باشند.")
        if kind in TRADE_ONLY and not trade:
            self.add_error("trade", "این نوع هشدار به معامله باز Paper نیاز دارد.")
        if threshold is not None:
            if kind in {"price", "rise", "fall"} | PROXIMITY and threshold <= 0:
                self.add_error("threshold", "آستانه باید مثبت باشد.")
            if kind in PROXIMITY and threshold > 100:
                self.add_error("threshold", "فاصله باید حداکثر ۱۰۰ درصد باشد.")
            if kind == "fall" and threshold >= 100:
                self.add_error("threshold", "کاهش باید کمتر از ۱۰۰ درصد باشد.")
        return values
