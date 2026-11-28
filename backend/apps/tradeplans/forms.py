import uuid
from datetime import timedelta

from django import forms
from django.utils import timezone

from apps.exchanges.models import ExchangeMarket, UserExchangeAccount
from apps.signals.models import Signal


class ManualTradeForm(forms.Form):
    account = forms.ModelChoiceField(
        label="حساب صرافی", queryset=UserExchangeAccount.objects.none()
    )
    market = forms.ModelChoiceField(label="ارز و جفت‌ارز", queryset=ExchangeMarket.objects.none())
    source = forms.ChoiceField(label="منبع", choices=[("manual", "ورود دستی")])
    entry_mode = forms.ChoiceField(
        label="روش ورود (پیش‌نمایش)",
        choices=[("limit", "Limit · قیمت مشخص"), ("market", "Market · قیمت فعلی برآوردی")],
        initial="limit",
        required=False,
    )
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
    capital = forms.IntegerField(
        label="مبلغ سرمایه (به ارز Quote)",
        min_value=1,
        widget=forms.NumberInput(attrs={"step": "1", "min": "1", "inputmode": "numeric"}),
    )
    leverage = forms.DecimalField(
        label="اهرم", max_digits=10, decimal_places=4, min_value=1, initial=1
    )
    trailing_sl = forms.BooleanField(label="Trailing SL", required=False)
    percentage_trailing = forms.BooleanField(label="Trailing", required=False)
    trailing_trigger = forms.ChoiceField(
        label="شروع Trailing",
        choices=(("tp1", "TP1"), ("tp2", "TP2"), ("tp3", "TP3")),
        required=False,
        initial="tp1",
    )
    trailing_distance = forms.IntegerField(
        label="فاصله Trailing (%)",
        min_value=1,
        max_value=99,
        initial=1,
        widget=forms.NumberInput(
            attrs={"step": "1", "min": "1", "max": "99", "inputmode": "numeric"}
        ),
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
            if key in {"entry_price", "tp1", "tp2", "tp3", "stop_loss", "leverage"}:
                field.widget.attrs.update({"inputmode": "decimal", "dir": "ltr"})
            if key in {"capital", "trailing_distance"}:
                field.widget.attrs.update({"inputmode": "numeric", "dir": "ltr", "step": "1"})
        self.fields["entry_price"].widget.attrs["data-no-draft"] = "1"
        if not self.is_bound:
            self.initial.setdefault("client_token", uuid.uuid4())

    def clean(self):
        data = super().clean()
        data["entry_mode"] = data.get("entry_mode") or "limit"
        account, market = data.get("account"), data.get("market")
        if market:
            pair = f"{market.base_asset.symbol}/{market.quote_asset.symbol}".upper()
            if market.symbol.upper() != pair:
                self.add_error("market", "جفت‌ارز با دارایی‌های پایه و مظنه بازار هم‌خوان نیست.")
            if not market.synced_at or market.synced_at < timezone.now() - timedelta(minutes=15):
                self.add_error("market", "اطلاعات بازار تازه نیست؛ حساب را همگام‌سازی کنید.")
            step = market.price_step
            if step is None or step <= 0:
                self.add_error("market", "گام قیمت بازار مشخص نیست؛ حساب را همگام‌سازی کنید.")
            else:
                for name in ("entry_price", "tp1", "tp2", "tp3", "stop_loss"):
                    price = data.get(name)
                    if price is not None and price % step != 0:
                        self.add_error(name, "قیمت با گام بازار صرافی سازگار نیست.")
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
        entry, stop = data.get("entry_price"), data.get("stop_loss")
        targets = (data.get("tp1"), data.get("tp2"), data.get("tp3"))
        if entry is not None and stop is not None and data.get("side"):
            side = data["side"]
            if (side == "long" and stop >= entry) or (side == "short" and stop <= entry):
                self.add_error(
                    "stop_loss", "حد ضرر باید در سمت مخالف جهت معامله نسبت به ورود باشد."
                )
            ordered = [target for target in targets if target is not None]
            if any((target <= entry if side == "long" else target >= entry) for target in ordered):
                self.add_error("tp1", "هدف‌ها باید در سمت سود نسبت به ورود باشند.")
            if ordered != sorted(set(ordered), reverse=side == "short"):
                self.add_error("tp1", "هدف‌ها باید به ترتیب و بدون تکرار باشند.")
        if targets[2] and not targets[1]:
            self.add_error("tp3", "TP3 بدون TP2 معتبر نیست.")
        trigger = data.get("trailing_trigger") or "tp1"
        data["trailing_trigger"] = trigger
        if data.get("percentage_trailing"):
            available = 1 + int(targets[1] is not None) + int(targets[2] is not None)
            trigger_position = {"tp1": 1, "tp2": 2, "tp3": 3}.get(trigger, 0)
            if not trigger_position or trigger_position > available:
                self.add_error(
                    "trailing_trigger",
                    "شروع Trailing باید یکی از TPهای تعریف‌شده همین معامله باشد.",
                )
        return data
