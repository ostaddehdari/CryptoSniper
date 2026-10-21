import uuid
from decimal import Decimal

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from .models import Exchange, ExchangeMarket, UserExchangeAccount
from .security import set_account_credentials


class ExchangeConnectionForm(forms.Form):
    exchange = forms.ModelChoiceField(
        label="صرافی",
        queryset=Exchange.objects.none(),
        widget=forms.Select(attrs={"class": "input"}),
    )
    label = forms.CharField(
        label="نام این اتصال",
        max_length=80,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "مثلاً حساب اصلی Bitunix"}),
    )
    environment = forms.ChoiceField(
        label="محیط",
        choices=((UserExchangeAccount.Environment.LIVE, "حساب واقعی"),),
        initial=UserExchangeAccount.Environment.LIVE,
        widget=forms.HiddenInput(),
    )
    api_key = forms.CharField(
        label="API Key",
        required=False,
        strip=True,
        widget=forms.TextInput(
            attrs={"class": "input", "autocomplete": "off", "spellcheck": "false"}
        ),
    )
    api_secret = forms.CharField(
        label="API Secret",
        required=False,
        strip=True,
        widget=forms.PasswordInput(
            attrs={"class": "input", "autocomplete": "new-password", "spellcheck": "false"}
        ),
    )
    passphrase = forms.CharField(
        label="Passphrase در صورت نیاز",
        required=False,
        strip=True,
        widget=forms.PasswordInput(
            attrs={"class": "input", "autocomplete": "new-password", "spellcheck": "false"}
        ),
    )
    no_withdrawal_confirmed = forms.BooleanField(
        label="تأیید می‌کنم مجوز برداشت این کلید خاموش است",
        required=False,
    )
    ip_restricted_confirmed = forms.BooleanField(
        label="کلید را به IP ثابت سرور محدود کرده‌ام",
        required=False,
    )

    def __init__(self, owner, *args, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)
        self.fields["exchange"].queryset = Exchange.objects.filter(enabled=True).exclude(adapter_code__in=("simulator", "binance"))

    def clean(self):
        cleaned = super().clean()
        exchange = cleaned.get("exchange")
        environment = cleaned.get("environment")
        if not exchange:
            return cleaned
        if environment != UserExchangeAccount.Environment.LIVE:
            self.add_error("environment", "فقط حساب واقعی در CryptoSniper فعال است.")
        elif exchange.adapter_code in {"simulator", "binance"}:
            self.add_error("exchange", "این اتصال در رابط جدید قابل افزودن نیست.")
        elif not cleaned.get("api_key"):
            self.add_error("api_key", "API Key یا Token برای صرافی واقعی لازم است.")
        elif exchange.adapter_code != "nobitex" and not cleaned.get("api_secret"):
            self.add_error("api_secret", "API Secret برای این صرافی لازم است.")
        elif exchange.adapter_code == "weex" and not cleaned.get("passphrase"):
            self.add_error("passphrase", "Passphrase برای WEEX لازم است.")
        elif not cleaned.get("no_withdrawal_confirmed"):
            self.add_error("no_withdrawal_confirmed", "کلید واقعی نباید مجوز برداشت داشته باشد.")
        label = cleaned.get("label", "").strip()
        if (
            exchange
            and UserExchangeAccount.objects.filter(
                owner=self.owner, exchange=exchange, label=label
            ).exists()
        ):
            self.add_error("label", "اتصالی با این نام قبلاً ساخته شده است.")
        return cleaned

    def save(self):
        account = UserExchangeAccount(
            owner=self.owner,
            exchange=self.cleaned_data["exchange"],
            label=self.cleaned_data["label"].strip(),
            environment=self.cleaned_data["environment"],
        )
        set_account_credentials(
            account,
            {
                "api_key": self.cleaned_data.get("api_key", ""),
                "api_secret": self.cleaned_data.get("api_secret", ""),
                "passphrase": self.cleaned_data.get("passphrase", ""),
                "no_withdrawal_confirmed": (
                    "true" if self.cleaned_data.get("no_withdrawal_confirmed") else ""
                ),
                "ip_restricted_confirmed": (
                    "true" if self.cleaned_data.get("ip_restricted_confirmed") else ""
                ),
            },
        )
        account.save()
        return account


class LiveSpotOrderForm(forms.Form):
    market = forms.ModelChoiceField(label="بازار Spot", queryset=ExchangeMarket.objects.none())
    side = forms.ChoiceField(label="جهت", choices=(("buy", "خرید"), ("sell", "فروش")))
    amount = forms.DecimalField(label="مقدار ارز پایه", min_value=Decimal("0.0000000000000001"))
    price = forms.DecimalField(label="قیمت Limit", min_value=Decimal("0.0000000000000001"))
    request_key = forms.UUIDField(widget=forms.HiddenInput)
    confirmed = forms.BooleanField(label="ریسک سفارش واقعی را تأیید می‌کنم")

    def __init__(self, owner, account, *args, **kwargs):
        self.owner, self.account = owner, account
        super().__init__(*args, **kwargs)
        self.fields["market"].queryset = ExchangeMarket.objects.filter(
            exchange=account.exchange, market_type="spot", active=True
        ).select_related("base_asset", "quote_asset")
        self.fields["market"].widget.attrs["class"] = "input"
        for name in ("side", "amount", "price"):
            self.fields[name].widget.attrs["class"] = "input"
        self.initial.setdefault("request_key", uuid.uuid4())

    def clean(self):
        cleaned = super().clean()
        account = self.account
        if not settings.LIVE_TRADING_ENABLED:
            raise ValidationError("ارسال سفارش واقعی در تنظیمات سرور خاموش است.")
        if account.owner_id != self.owner.pk or account.environment != "live":
            raise ValidationError("حساب Live متعلق به کاربر لازم است.")
        if account.status != "connected" or not account.trading_enabled:
            raise ValidationError("ابتدا مجوز Read+Spot و نبود مجوز برداشت را همگام‌سازی کنید.")
        if account.permissions.get("can_withdraw") is not False:
            raise ValidationError("مجوز برداشت باید صریحاً خاموش و توسط API گزارش شود.")
        market = cleaned.get("market")
        amount, price = cleaned.get("amount"), cleaned.get("price")
        if not market or amount is None or price is None:
            return cleaned
        if market.exchange_id != account.exchange_id:
            raise ValidationError("بازار با حساب صرافی هم‌خوان نیست.")
        if market.amount_step and amount % market.amount_step:
            self.add_error("amount", "مقدار با Lot Step صرافی سازگار نیست.")
        if market.price_step and price % market.price_step:
            self.add_error("price", "قیمت با Tick Size صرافی سازگار نیست.")
        if market.min_amount and amount < market.min_amount:
            self.add_error("amount", "مقدار از حداقل بازار کمتر است.")
        if market.min_notional and amount * price < market.min_notional:
            self.add_error("amount", "ارزش سفارش از Min Notional کمتر است.")
        return cleaned
