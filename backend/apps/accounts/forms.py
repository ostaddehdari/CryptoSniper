from zoneinfo import available_timezones

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password

from .models import User


class SignInForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "نام کاربری"
        self.fields["username"].widget.attrs.update(
            {
                "placeholder": "نام کاربری خود را وارد کنید",
                "autocomplete": "username",
                "class": "input",
                "autofocus": True,
            }
        )
        self.fields["password"].label = "رمز عبور"
        self.fields["password"].widget.attrs.update(
            {
                "placeholder": "رمز عبور",
                "autocomplete": "current-password",
                "class": "input",
            }
        )

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.account_status != User.AccountStatus.ACTIVE:
            raise forms.ValidationError("این حساب در دسترس نیست.", code="account_unavailable")


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("display_name", "email", "timezone", "base_currency", "theme")
        widgets = {
            "display_name": forms.TextInput(attrs={"class": "input", "autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"class": "input", "autocomplete": "email"}),
            "timezone": forms.Select(attrs={"class": "input"}),
            "base_currency": forms.Select(
                choices=(("USDT", "USDT"), ("USDC", "USDC"), ("BTC", "BTC")),
                attrs={"class": "input"},
            ),
            "theme": forms.Select(attrs={"class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        preferred = ["Asia/Tehran", "Asia/Dubai", "Europe/London", "UTC"]
        zones = [zone for zone in preferred if zone in available_timezones()]
        current = self.instance.timezone
        if current and current not in zones:
            zones.append(current)
        self.fields["timezone"].widget.choices = [(zone, zone) for zone in zones]
        for field in self.fields.values():
            field.required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("این ایمیل قبلاً ثبت شده است.")
        return email


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        label="ایمیل حساب",
        widget=forms.EmailInput(
            attrs={"class": "input", "autocomplete": "email", "placeholder": "name@example.com"}
        ),
    )

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class SetNewPasswordForm(forms.Form):
    password = forms.CharField(
        label="رمز عبور جدید",
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "input", "autocomplete": "new-password"}),
    )
    password_confirm = forms.CharField(
        label="تکرار رمز عبور",
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "input", "autocomplete": "new-password"}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        if password and password != cleaned.get("password_confirm"):
            self.add_error("password_confirm", "تکرار رمز عبور یکسان نیست.")
        if password:
            validate_password(password, self.user)
        return cleaned
