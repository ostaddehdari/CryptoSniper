import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

from apps.accounts.models import UserOwnedModel
from apps.core.security import validate_public_https_url

symbol_validator = RegexValidator(
    r"^[A-Z0-9]{2,20}$", "نماد باید فقط شامل حروف بزرگ لاتین و عدد باشد."
)


class Exchange(models.Model):
    code = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=80)
    website = models.URLField(blank=True, validators=(validate_public_https_url,))
    adapter_code = models.SlugField(max_length=32, unique=True)
    spot_supported = models.BooleanField(default=True)
    margin_supported = models.BooleanField(default=False)
    futures_supported = models.BooleanField(default=False)
    sandbox_supported = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def supports_market(self, market_type):
        return {
            ExchangeMarket.MarketType.SPOT: self.spot_supported,
            ExchangeMarket.MarketType.MARGIN: self.margin_supported,
        }.get(market_type, False)


class Asset(models.Model):
    symbol = models.CharField(max_length=20, unique=True, validators=(symbol_validator,))
    name = models.CharField(max_length=80, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("symbol",)

    def __str__(self):
        return self.symbol

    def save(self, *args, **kwargs):
        self.symbol = self.symbol.strip().upper()
        return super().save(*args, **kwargs)


class ExchangeMarket(models.Model):
    class MarketType(models.TextChoices):
        SPOT = "spot", "Spot"
        MARGIN = "margin", "Margin"

    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE, related_name="markets")
    symbol = models.CharField(max_length=48)
    base_asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="base_markets")
    quote_asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="quote_markets")
    market_type = models.CharField(max_length=12, choices=MarketType.choices)
    min_amount = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    max_amount = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    amount_step = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    price_step = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    min_notional = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    max_leverage = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal("1"),
        validators=(MinValueValidator(Decimal("1")),),
    )
    maker_fee = models.DecimalField(max_digits=12, decimal_places=8, null=True, blank=True)
    taker_fee = models.DecimalField(max_digits=12, decimal_places=8, null=True, blank=True)
    active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("exchange__name", "symbol", "market_type")
        constraints = [
            models.UniqueConstraint(
                fields=("exchange", "symbol", "market_type"),
                name="exchange_market_symbol_type_unique",
            ),
            models.CheckConstraint(
                condition=Q(market_type__in=("spot", "margin")),
                name="exchange_market_v1_type_supported",
            ),
            models.CheckConstraint(
                condition=Q(max_leverage__gte=1),
                name="exchange_market_leverage_at_least_one",
            ),
        ]
        indexes = [models.Index(fields=("exchange", "symbol", "market_type", "active"))]

    def __str__(self):
        return f"{self.exchange.code}:{self.symbol}:{self.market_type}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        self.symbol = self.symbol.strip().upper()
        if not self.exchange.supports_market(self.market_type):
            raise ValidationError("این نوع بازار توسط صرافی پشتیبانی نمی‌شود.")
        if self.market_type == self.MarketType.SPOT and self.max_leverage != Decimal("1"):
            raise ValidationError("بازار Spot در نسخه نخست اهرم ندارد.")


class UserExchangeAccount(UserOwnedModel):
    class Environment(models.TextChoices):
        PAPER = "paper", "شبیه‌ساز"
        SANDBOX = "sandbox", "آزمایشی صرافی"
        LIVE = "live", "حساب اصلی"

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار بررسی"
        CONNECTED = "connected", "متصل"
        RESTRICTED = "restricted", "محدود"
        ERROR = "error", "خطا"
        DISABLED = "disabled", "غیرفعال"

    exchange = models.ForeignKey(Exchange, on_delete=models.PROTECT, related_name="accounts")
    label = models.CharField(max_length=80)
    environment = models.CharField(
        max_length=12, choices=Environment.choices, default=Environment.LIVE
    )
    credentials_encrypted = models.TextField(blank=True, editable=False)
    credential_hint = models.CharField(max_length=24, blank=True, editable=False)
    credential_key_version = models.PositiveSmallIntegerField(default=1, editable=False)
    trading_enabled = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    permissions = models.JSONField(default=dict, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=80, blank=True)
    last_error_message = models.CharField(max_length=240, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "exchange", "label"),
                name="user_exchange_account_label_unique",
            )
        ]
        indexes = [models.Index(fields=("owner", "status", "exchange"))]

    def clean(self):
        super().clean()
        self.label = self.label.strip()
        if self.environment == self.Environment.SANDBOX and not self.exchange.sandbox_supported:
            raise ValidationError({"environment": "این صرافی محیط آزمایشی اعلام‌شده ندارد."})
        if self.exchange.futures_supported and not (
            self.exchange.spot_supported or self.exchange.margin_supported
        ):
            raise ValidationError("صرافی فقط-Futures در نسخه نخست مجاز نیست.")

    def save(self, *args, **kwargs):
        self.full_clean(exclude=("credentials_encrypted",))
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.label} · {self.exchange.name}"


class BalanceSnapshot(models.Model):
    wallet_scope = models.CharField(
        max_length=12, choices=[("spot", "Spot"), ("margin", "Margin")], default="spot"
    )
    exchange_account = models.ForeignKey(
        UserExchangeAccount, on_delete=models.CASCADE, related_name="balance_snapshots"
    )
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="balance_snapshots")
    free_balance = models.DecimalField(max_digits=32, decimal_places=16, default=0)
    locked_balance = models.DecimalField(max_digits=32, decimal_places=16, default=0)
    total_balance = models.DecimalField(max_digits=32, decimal_places=16, default=0)
    usd_value = models.DecimalField(max_digits=32, decimal_places=8, null=True, blank=True)
    captured_at = models.DateTimeField()

    class Meta:
        ordering = ("-captured_at", "asset__symbol")
        constraints = [
            models.UniqueConstraint(
                fields=("exchange_account", "asset", "wallet_scope", "captured_at"),
                name="balance_snapshot_account_wallet_time_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(free_balance__gte=0) & Q(locked_balance__gte=0) & Q(total_balance__gte=0)
                ),
                name="balance_snapshot_nonnegative",
            ),
        ]
        indexes = [models.Index(fields=("exchange_account", "captured_at"))]

    def __str__(self):
        return f"{self.exchange_account_id}:{self.asset}:{self.captured_at.isoformat()}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.total_balance != self.free_balance + self.locked_balance:
            raise ValidationError("موجودی کل باید برابر مجموع آزاد و قفل‌شده باشد.")


class LiveSpotOrder(models.Model):
    """Durable direct Spot order. Unknown outcomes are never auto-retried."""

    class State(models.TextChoices):
        PENDING = "pending", "در صف"
        SUBMITTING = "submitting", "در حال ارسال"
        OPEN = "open", "باز"
        PARTIAL = "partial", "بخشی اجرا شده"
        FILLED = "filled", "تکمیل‌شده"
        CANCELLED = "cancelled", "لغوشده"
        UNCERTAIN = "uncertain", "نتیجه نامعلوم"
        FAILED = "failed", "ناموفق"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    account = models.ForeignKey(UserExchangeAccount, on_delete=models.PROTECT)
    market = models.ForeignKey(ExchangeMarket, on_delete=models.PROTECT)
    request_key = models.UUIDField(default=uuid.uuid4)
    client_order_id = models.CharField(max_length=80)
    external_order_id = models.CharField(max_length=120, blank=True)
    side = models.CharField(max_length=4, choices=(("buy", "خرید"), ("sell", "فروش")))
    order_type = models.CharField(max_length=8, choices=(("limit", "Limit"), ("market", "Market")))
    amount = models.DecimalField(max_digits=32, decimal_places=16)
    price = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    filled_amount = models.DecimalField(max_digits=32, decimal_places=16, default=0)
    average_price = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    state = models.CharField(max_length=16, choices=State.choices, default=State.PENDING)
    error_code = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "request_key"), name="live_spot_order_owner_request_unique"
            ),
            models.UniqueConstraint(
                fields=("account", "client_order_id"),
                name="live_spot_order_account_client_unique",
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="live_spot_order_amount_positive"
            ),
            models.CheckConstraint(
                condition=Q(price__isnull=True) | Q(price__gt=0),
                name="live_spot_order_price_positive",
            ),
            models.CheckConstraint(
                condition=Q(filled_amount__gte=0), name="live_spot_order_filled_nonnegative"
            ),
        ]

    def __str__(self):
        return f"{self.account.exchange.code}:{self.client_order_id}"
