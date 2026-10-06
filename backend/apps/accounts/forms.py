from django.contrib.auth.forms import AuthenticationForm


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
