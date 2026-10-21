from decimal import Decimal

from django import forms

from apps.exchanges.models import ExchangeMarket, UserExchangeAccount

from .channel_parser import apply_channel_template, template_matches
from .models import SignalSource, TelegramChannel, TelegramChannelTemplate


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
        strip=False,
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


class TelegramConnectForm(forms.Form):
    api_id = forms.IntegerField(label="Telegram API ID", min_value=1)
    api_hash = forms.CharField(
        label="Telegram API Hash",
        max_length=128,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    phone = forms.CharField(
        label="شماره با کد کشور",
        max_length=32,
        widget=forms.TextInput(attrs={"placeholder": "+98…", "autocomplete": "tel"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"


class TelegramCodeForm(forms.Form):
    code = forms.CharField(
        label="کد ورود Telegram",
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code"}),
    )
    password = forms.CharField(
        label="رمز دومرحله‌ای (اگر فعال است)",
        max_length=256,
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"

    def clean_code(self):
        code = "".join(str(self.cleaned_data.get("code", "")).split())
        if code and (not code.isdigit() or not 3 <= len(code) <= 20):
            raise forms.ValidationError("کد ورود باید فقط شامل رقم باشد.")
        return code


class TelegramChannelForm(forms.Form):
    peer_id = forms.ChoiceField(label="کانال قابل دسترس")
    parse_mode = forms.ChoiceField(label="روش تحلیل", choices=TelegramChannel.ParseMode.choices)
    automation = forms.ChoiceField(label="اتوماسیون", choices=TelegramChannel.Automation.choices)
    template = forms.JSONField(
        label="قالب JSON",
        required=False,
        initial={"version": "1", "aliases": {}},
        widget=forms.Textarea(attrs={"rows": 5}),
    )
    min_confidence = forms.IntegerField(label="حداقل اطمینان فنی", min_value=0, max_value=100)
    paper_capital = forms.DecimalField(
        label="بودجه Legacy Full-Auto (غیرفعال)",
        max_digits=32,
        decimal_places=16,
        min_value=Decimal("0.00000001"),
    )

    def __init__(self, channel_choices=(), *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["peer_id"].choices = list(channel_choices)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"


class TelegramTemplateForm(forms.Form):
    channel_id = forms.IntegerField(widget=forms.HiddenInput)
    name = forms.CharField(label="نام قالب", max_length=80)
    priority = forms.IntegerField(label="اولویت", min_value=1, max_value=1000, initial=100)
    message_kind = forms.ChoiceField(
        label="نوع پیام", choices=TelegramChannelTemplate.MessageKind.choices
    )
    definition = forms.JSONField(
        label="تعریف JSON",
        initial={"version": "1", "required_markers": [], "exclude_markers": [], "aliases": {}},
        widget=forms.Textarea(attrs={"rows": 6}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"

    def clean_definition(self):
        definition = self.cleaned_data["definition"]
        template_matches("preview", definition)
        apply_channel_template("BTC/USDT ENTRY 10 TARGET 11 STOP LOSS 9 LONG", definition)
        return definition
