from django import forms

from .models import Exchange, UserExchangeAccount
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
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "مثلاً حساب اصلی یا تمرین"}),
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
        elif not cleaned.get("api_key") or not cleaned.get("api_secret"):
            self.add_error("api_key", "API Key و Secret برای صرافی واقعی لازم است.")
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
            },
        )
        account.save()
        return account
