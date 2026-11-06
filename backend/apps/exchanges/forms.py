import uuid
from decimal import Decimal

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Exchange, ExchangeMarket, UserExchangeAccount
from .security import set_account_credentials


class ExchangeConnectionForm(forms.Form):
    exchange = forms.ModelChoiceField(
        label="صرافی",
        queryset=Exchange.objects.none(),
        widget=forms.Select(attrs={"class": "input"}),
    )
    environment = forms.ChoiceField(
        label="محیط",
        choices=UserExchangeAccount.Environment.choices,
        widget=forms.Select(attrs={"class": "input"}),
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
        self.fields["exchange"].queryset = Exchange.objects.filter(enabled=True)

    def clean(self):
        cleaned = super().clean()
        exchange = cleaned.get("exchange")
        environment = cleaned.get("environment")
        if not exchange:
            return cleaned
        if exchange.adapter_code == "simulator":
            cleaned["environment"] = UserExchangeAccount.Environment.PAPER
            cleaned["api_key"] = ""
            cleaned["api_secret"] = ""
            cleaned["passphrase"] = ""
        elif environment == UserExchangeAccount.Environment.PAPER:
            self.add_error("environment", "برای Paper، شبیه‌ساز CryptoSniper را انتخاب کنید.")
        elif (
            environment == UserExchangeAccount.Environment.SANDBOX
            and not exchange.sandbox_supported
        ):
            self.add_error("environment", "این Adapter هنوز Sandbox تأییدشده ندارد.")
        elif not cleaned.get("api_key"):
            self.add_error("api_key", "API Key یا Token برای صرافی واقعی لازم است.")
        elif exchange.adapter_code != "nobitex" and not cleaned.get("api_secret"):
            self.add_error("api_secret", "API Secret برای این صرافی لازم است.")
        elif exchange.adapter_code == "weex" and not cleaned.get("passphrase"):
            self.add_error("passphrase", "Passphrase برای WEEX لازم است.")
        elif not cleaned.get("no_withdrawal_confirmed"):
            self.add_error("no_withdrawal_confirmed", "کلید واقعی نباید مجوز برداشت داشته باشد.")
        return cleaned

    @staticmethod
    def _next_label(owner, exchange):
        used = set(
            UserExchangeAccount.objects.filter(owner=owner, exchange=exchange).values_list(
                "label", flat=True
            )
        )
        if exchange.name not in used:
            return exchange.name
        number = 2
        while f"{exchange.name} {number}" in used:
            number += 1
        return f"{exchange.name} {number}"

    @transaction.atomic
    def save(self):
        exchange = self.cleaned_data["exchange"]
        account = (
            UserExchangeAccount.objects.select_for_update()
            .filter(
                owner=self.owner,
                exchange=exchange,
                status=UserExchangeAccount.Status.DISABLED,
            )
            .order_by("-updated_at", "-pk")
            .first()
        )
        if account is None:
            account = UserExchangeAccount(
                owner=self.owner,
                exchange=exchange,
                label=self._next_label(self.owner, exchange),
            )
        account.environment = self.cleaned_data["environment"]
        account.status = UserExchangeAccount.Status.PENDING
        account.trading_enabled = False
        account.permissions = {}
        account.last_verified_at = None
        account.last_sync_at = None
        account.last_error_code = ""
        account.last_error_message = ""
        account.last_error_at = None
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
    order_type = forms.ChoiceField(
        label="نوع سفارش",
        choices=(("limit", "Limit"), ("market", "Market")),
        initial="limit",
        required=False,
    )
    price = forms.DecimalField(
        label="قیمت Limit", min_value=Decimal("0.0000000000000001"), required=False
    )
    reference_price = forms.DecimalField(
        label="قیمت مرجع Market", min_value=Decimal("0.0000000000000001"), required=False
    )
    request_key = forms.UUIDField(widget=forms.HiddenInput)
    confirmed = forms.BooleanField(label="ریسک سفارش واقعی را تأیید می‌کنم")

    def __init__(self, owner, account, *args, **kwargs):
        self.owner, self.account = owner, account
        super().__init__(*args, **kwargs)
        self.fields["market"].queryset = ExchangeMarket.objects.filter(
            exchange=account.exchange, market_type="spot", active=True
        ).select_related("base_asset", "quote_asset")
        self.fields["market"].widget.attrs["class"] = "input"
        for name in ("side", "order_type", "amount", "price", "reference_price"):
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
        if account.permissions.get("can_read") is not True:
            raise ValidationError("مجوز Read حساب تأیید نشده است.")
        if account.permissions.get("can_trade_spot") is not True:
            raise ValidationError("مجوز Spot Trading این حساب تأیید نشده است.")
        if account.permissions.get("can_withdraw") is not False:
            raise ValidationError("مجوز برداشت باید صریحاً خاموش و توسط API گزارش شود.")
        market = cleaned.get("market")
        amount, price = cleaned.get("amount"), cleaned.get("price")
        reference = cleaned.get("reference_price")
        order_type = cleaned.get("order_type") or "limit"
        cleaned["order_type"] = order_type
        if order_type == "limit" and price is None:
            self.add_error("price", "قیمت سفارش Limit الزامی است.")
        if order_type == "market" and reference is None:
            self.add_error("reference_price", "قیمت مرجع تازه برای Market الزامی است.")
        if not market or amount is None or (price is None and reference is None):
            return cleaned
        if market.exchange_id != account.exchange_id:
            raise ValidationError("بازار با حساب صرافی هم‌خوان نیست.")
        if market.amount_step and amount % market.amount_step:
            self.add_error("amount", "مقدار با Lot Step صرافی سازگار نیست.")
        if order_type == "limit" and market.price_step and price % market.price_step:
            self.add_error("price", "قیمت با Tick Size صرافی سازگار نیست.")
        if market.min_amount and amount < market.min_amount:
            self.add_error("amount", "مقدار از حداقل بازار کمتر است.")
        execution_reference = price if order_type == "limit" else reference
        if market.min_notional and amount * execution_reference < market.min_notional:
            self.add_error("amount", "ارزش سفارش از Min Notional کمتر است.")
        return cleaned
