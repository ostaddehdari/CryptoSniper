from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower


class OwnedQuerySet(models.QuerySet):
    def for_user(self, user):
        if not getattr(user, "is_authenticated", False):
            return self.none()
        return self.filter(owner=user)


class UserOwnedModel(models.Model):
    """Base for private records: every query can be scoped to its owner."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    objects = OwnedQuerySet.as_manager()

    class Meta:
        abstract = True


class User(AbstractUser):
    class AccountStatus(models.TextChoices):
        ACTIVE = "active", "فعال"
        SUSPENDED = "suspended", "تعلیق‌شده"
        CLOSED = "closed", "بسته‌شده"

    class Theme(models.TextChoices):
        LIGHT = "light", "روشن"
        DARK = "dark", "تیره"

    email = models.EmailField("ایمیل", blank=True)
    display_name = models.CharField("نام نمایشی", max_length=80, blank=True)
    timezone = models.CharField("منطقه زمانی", max_length=64, default="Asia/Tehran")
    base_currency = models.CharField("ارز پایه", max_length=12, default="USDT")
    account_status = models.CharField(
        "وضعیت حساب", max_length=16, choices=AccountStatus.choices, default=AccountStatus.ACTIVE
    )
    theme = models.CharField("ظاهر", max_length=8, choices=Theme.choices, default=Theme.LIGHT)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=~models.Q(email=""),
                name="accounts_user_email_ci_unique",
            )
        ]

    def clean(self):
        super().clean()
        if self.email:
            self.email = self.email.strip().lower()
        self.base_currency = self.base_currency.strip().upper()
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValidationError({"timezone": "منطقه زمانی معتبر نیست."}) from error

    @property
    def preferred_name(self):
        return self.display_name or self.get_full_name() or self.username
