import re
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


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


def password_reset_expiry():
    return timezone.now() + timedelta(minutes=30)


class PasswordResetRequest(UserOwnedModel):
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=password_reset_expiry)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=("owner", "created_at"))]

    def __str__(self):
        return f"password reset {self.pk} for user {self.owner_id}"

    @property
    def is_usable(self):
        return self.used_at is None and self.expires_at > timezone.now()


class UserSession(UserOwnedModel):
    session_key = models.CharField(max_length=40, unique=True, editable=False)
    user_agent_label = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=("owner", "revoked_at", "last_seen_at"))]

    def __str__(self):
        return f"session {self.pk} for user {self.owner_id}"

    @property
    def is_currently_valid(self):
        return self.revoked_at is None and self.expires_at > timezone.now()


class TradingPreferences(UserOwnedModel):
    class Market(models.TextChoices):
        SPOT = "spot", "Spot"
        MARGIN = "margin", "Margin"

    class TrailingTrigger(models.TextChoices):
        TP1 = "tp1", "پس از TP1"

    default_order_amount = models.DecimalField(
        "مبلغ پیش‌فرض معامله",
        max_digits=20,
        decimal_places=8,
        default=Decimal("50"),
        validators=(MinValueValidator(Decimal("0")),),
    )
    default_market = models.CharField(
        "بازار پیش‌فرض", max_length=12, choices=Market.choices, default=Market.SPOT
    )
    tp1_percent = models.DecimalField(
        "سهم TP1", max_digits=5, decimal_places=2, default=Decimal("10")
    )
    tp2_percent = models.DecimalField(
        "سهم TP2", max_digits=5, decimal_places=2, default=Decimal("10")
    )
    tp3_percent = models.DecimalField(
        "سهم TP3", max_digits=5, decimal_places=2, default=Decimal("80")
    )
    trailing_sl_enabled = models.BooleanField("Trailing SL", default=True)
    trailing_tp_enabled = models.BooleanField("Trailing TP", default=True)
    trailing_trigger = models.CharField(
        "شروع Trailing",
        max_length=8,
        choices=TrailingTrigger.choices,
        default=TrailingTrigger.TP1,
    )
    trailing_distance_percent = models.DecimalField(
        "فاصله Trailing",
        max_digits=6,
        decimal_places=3,
        default=Decimal("1"),
        validators=(MinValueValidator(Decimal("0.001")),),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("owner",), name="one_trading_preferences_per_user"),
            models.CheckConstraint(
                condition=models.Q(default_order_amount__gte=0),
                name="trading_default_amount_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(tp1_percent__gte=0)
                    & models.Q(tp2_percent__gte=0)
                    & models.Q(tp3_percent__gte=0)
                ),
                name="trading_tp_percentages_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(trailing_distance_percent__gt=0),
                name="trading_trailing_distance_positive",
            ),
        ]

    def __str__(self):
        return f"trading preferences for user {self.owner_id}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        values = (self.tp1_percent, self.tp2_percent, self.tp3_percent)
        if any(value < 0 for value in values):
            raise ValidationError("درصدهای برداشت سود نمی‌توانند منفی باشند.")
        if sum(values) != Decimal("100"):
            raise ValidationError("مجموع سهم‌های TP باید دقیقاً ۱۰۰ درصد باشد.")


_SENSITIVE_AUDIT_KEY = re.compile(
    r"password|secret|token|api.?key|credential|authorization|cookie|session.?key", re.I
)
_SENSITIVE_AUDIT_VALUE = re.compile(
    r"(?i)(password|secret|token|api[_-]?key|authorization|cookie)\s*[:=]\s*[^\s,;]+"
)


def sanitize_audit_metadata(value, depth=0):
    if depth > 4:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        return {
            str(key)[:60]: (
                "[REDACTED]"
                if _SENSITIVE_AUDIT_KEY.search(str(key))
                else sanitize_audit_metadata(item, depth + 1)
            )
            for key, item in list(value.items())[:30]
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_audit_metadata(item, depth + 1) for item in value[:30]]
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    text = _SENSITIVE_AUDIT_VALUE.sub(r"\1=[REDACTED]", str(value))
    return text[:240]


class AppendOnlyAuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("رویدادهای Audit قابل ویرایش نیستند.")

    def delete(self):
        raise ValidationError("رویدادهای Audit قابل حذف نیستند.")


class AuditLog(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="audit_events",
    )
    event_type = models.CharField(
        max_length=64,
        validators=(RegexValidator(r"^[a-z0-9_.-]+$"),),
        editable=False,
    )
    metadata = models.JSONField(default=dict, blank=True, editable=False)
    ip_hash = models.CharField(max_length=64, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    objects = AppendOnlyAuditQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [models.Index(fields=("owner", "created_at"))]

    def __str__(self):
        return f"{self.event_type} at {self.created_at}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("رویدادهای Audit قابل ویرایش نیستند.")
        self.metadata = sanitize_audit_metadata(self.metadata)
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("رویدادهای Audit قابل حذف نیستند.")
