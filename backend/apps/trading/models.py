"""Stage 08: durable paper-only lifecycle. Production exchange orders are disabled."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Trade(models.Model):
    class State(models.TextChoices):
        QUEUED = "queued", "در صف"
        SUBMITTING = "submitting", "در حال ارسال شبیه‌ساز"
        PARTIAL = "partially_filled", "بخشی اجرا شده"
        OPEN = "open", "باز"
        UNCERTAIN = "uncertain", "نتیجه نامعلوم"
        FAILED = "failed", "ناموفق"
        CANCELLED = "cancelled", "لغوشده"
        CLOSED = "closed", "بسته‌شده"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="paper_trades"
    )
    account = models.ForeignKey("exchanges.UserExchangeAccount", on_delete=models.CASCADE)
    market = models.ForeignKey("exchanges.ExchangeMarket", on_delete=models.PROTECT)
    plan = models.ForeignKey(
        "tradeplans.TradePlan", on_delete=models.CASCADE, null=True, blank=True
    )
    signal = models.ForeignKey("signals.Signal", on_delete=models.CASCADE, null=True, blank=True)
    request_key = models.UUIDField(default=uuid.uuid4)
    request_hash = models.CharField(max_length=64)
    state = models.CharField(max_length=24, choices=State.choices, default=State.QUEUED)
    mode = models.CharField(max_length=12, default="paper", editable=False)
    side = models.CharField(max_length=8, default="buy")
    quantity = models.DecimalField(max_digits=32, decimal_places=16)
    entry_price = models.DecimalField(max_digits=32, decimal_places=16)
    capital_reserved = models.DecimalField(max_digits=32, decimal_places=16)
    snapshot = models.JSONField(default=dict)
    filled_quantity = models.DecimalField(max_digits=32, decimal_places=16, default=0)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "request_key"), name="paper_trade_owner_request_unique"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="paper_trade_quantity_positive"
            ),
            models.CheckConstraint(
                condition=Q(entry_price__gt=0), name="paper_trade_entry_positive"
            ),
            models.CheckConstraint(
                condition=Q(capital_reserved__gt=0), name="paper_trade_reserved_positive"
            ),
            models.CheckConstraint(
                condition=Q(filled_quantity__gte=0), name="paper_trade_filled_nonnegative"
            ),
        ]

    def __str__(self):
        return f"Paper Trade {self.pk} [{self.state}]"


class Order(models.Model):
    class State(models.TextChoices):
        QUEUED = "queued", "در صف"
        SUBMITTING = "submitting", "ارسال"
        PARTIAL = "partial", "بخشی اجرا شده"
        FILLED = "filled", "تکمیل‌شده"
        CANCELLED = "cancelled", "لغوشده"
        UNCERTAIN = "uncertain", "نامعلوم"
        FAILED = "failed", "ناموفق"

    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name="orders")
    account = models.ForeignKey("exchanges.UserExchangeAccount", on_delete=models.CASCADE)
    client_order_id = models.CharField(max_length=80)
    external_order_id = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=16, choices=State.choices, default=State.QUEUED)
    quantity = models.DecimalField(max_digits=32, decimal_places=16)
    filled_quantity = models.DecimalField(max_digits=32, decimal_places=16, default=0)
    price = models.DecimalField(max_digits=32, decimal_places=16)
    sent_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("account", "client_order_id"), name="paper_order_account_client_unique"
            ),
            models.UniqueConstraint(
                fields=("account", "external_order_id"),
                condition=~Q(external_order_id=""),
                name="paper_order_account_external_unique",
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="paper_order_qty_positive"),
            models.CheckConstraint(
                condition=Q(filled_quantity__gte=0), name="paper_order_filled_nonnegative"
            ),
        ]

    def __str__(self):
        return f"Paper Order {self.client_order_id}"


class OrderFill(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="fills")
    account = models.ForeignKey("exchanges.UserExchangeAccount", on_delete=models.CASCADE)
    exchange_fill_id = models.CharField(max_length=120)
    quantity = models.DecimalField(max_digits=32, decimal_places=16)
    price = models.DecimalField(max_digits=32, decimal_places=16)
    fee = models.DecimalField(max_digits=32, decimal_places=16, default=0)
    fee_asset = models.ForeignKey(
        "exchanges.Asset",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="entry_fee_fills",
    )
    fee_quote_rate = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    occurred_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("account", "exchange_fill_id"), name="paper_fill_account_provider_unique"
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="paper_fill_qty_positive"),
            models.CheckConstraint(condition=Q(fee__gte=0), name="paper_fill_fee_nonnegative"),
        ]

    def __str__(self):
        return f"Fill {self.exchange_fill_id}"


class Position(models.Model):
    trade = models.OneToOneField(Trade, on_delete=models.CASCADE, related_name="position")
    account = models.ForeignKey("exchanges.UserExchangeAccount", on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=32, decimal_places=16, default=0)
    average_entry = models.DecimalField(max_digits=32, decimal_places=16, default=0)
    total_fees = models.DecimalField(max_digits=32, decimal_places=16, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Paper Position {self.trade_id}"


class CapitalReservation(models.Model):
    """Paper collateral ledger persists consumed allocation after fills."""

    trade = models.OneToOneField(Trade, on_delete=models.CASCADE, related_name="reservation")
    account = models.ForeignKey("exchanges.UserExchangeAccount", on_delete=models.CASCADE)
    quote_asset = models.ForeignKey("exchanges.Asset", on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=32, decimal_places=16)
    active = models.BooleanField(default=True)
    spent = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="paper_reservation_positive"),
        ]

    def __str__(self):
        return f"Paper reservation {self.trade_id}"


class PaperMarginLoan(models.Model):
    """Deterministic Paper-only borrow ledger; never represents provider debt."""

    class State(models.TextChoices):
        ACTIVE = "active", "فعال"
        REPAID = "repaid", "بازپرداخت‌شده"

    trade = models.OneToOneField(Trade, on_delete=models.CASCADE, related_name="margin_loan")
    account = models.ForeignKey("exchanges.UserExchangeAccount", on_delete=models.CASCADE)
    asset = models.ForeignKey("exchanges.Asset", on_delete=models.PROTECT)
    principal = models.DecimalField(max_digits=32, decimal_places=16)
    accrued_interest = models.DecimalField(max_digits=32, decimal_places=16, default=0)
    repaid_amount = models.DecimalField(max_digits=32, decimal_places=16, default=0)
    hourly_rate = models.DecimalField(max_digits=16, decimal_places=12, default="0.0001")
    state = models.CharField(max_length=12, choices=State.choices, default=State.ACTIVE)
    opened_at = models.DateTimeField(default=timezone.now)
    repaid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(principal__gt=0), name="paper_margin_principal_positive"
            ),
            models.CheckConstraint(
                condition=Q(accrued_interest__gte=0) & Q(repaid_amount__gte=0),
                name="paper_margin_settlement_nonnegative",
            ),
        ]

    def __str__(self):
        return f"Paper Margin loan {self.trade_id} [{self.state}]"


class ExecutionOutbox(models.Model):
    class State(models.TextChoices):
        PENDING = "pending", "در صف"
        INFLIGHT = "inflight", "در حال انجام"
        DONE = "done", "انجام‌شده"
        UNCERTAIN = "uncertain", "نتیجه نامعلوم"
        ERROR = "error", "خطا"

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="outbox")
    state = models.CharField(max_length=12, choices=State.choices, default=State.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    last_error_code = models.CharField(max_length=50, blank=True)
    fence = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    dead_letter = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Outbox {self.order_id}: {self.state}"


class TradeEvent(models.Model):
    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=42)
    payload = models.JSONField(default=dict)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("pk",)

    def __str__(self):
        return f"Trade {self.trade_id}: {self.event_type}"


class PaperRiskPolicy(models.Model):
    """Small operator-controlled limits. Never grants real order permissions."""

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="paper_risk_policy"
    )
    max_active_trades = models.PositiveSmallIntegerField(default=5)
    max_capital_per_trade = models.DecimalField(max_digits=32, decimal_places=16, default=500)
    max_total_allocated = models.DecimalField(max_digits=32, decimal_places=16, default=5000)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(max_active_trades__gte=1) & Q(max_active_trades__lte=20),
                name="paper_risk_trade_limit_range",
            ),
            models.CheckConstraint(
                condition=Q(max_capital_per_trade__gt=0), name="paper_risk_single_capital_positive"
            ),
            models.CheckConstraint(
                condition=Q(max_total_allocated__gt=0), name="paper_risk_total_capital_positive"
            ),
        ]

    def __str__(self):
        return f"Paper risk limits for user {self.owner_id}"


class TradeTarget(models.Model):
    """Execution-independent immutable allocation with mutable progress (Paper only)."""

    class State(models.TextChoices):
        WAITING = "waiting", "منتظر"
        PARTIAL = "partial", "بخشی اجرا شد"
        FILLED = "filled", "تکمیل"
        CANCELLED = "cancelled", "لغو"

    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name="targets")
    position = models.PositiveSmallIntegerField()
    price = models.DecimalField(max_digits=32, decimal_places=16)
    share_percent = models.DecimalField(max_digits=5, decimal_places=2)
    allocated_quantity = models.DecimalField(max_digits=32, decimal_places=16)
    filled_quantity = models.DecimalField(max_digits=32, decimal_places=16, default=0)
    state = models.CharField(max_length=12, choices=State.choices, default=State.WAITING)

    class Meta:
        ordering = ("position",)
        constraints = [
            models.UniqueConstraint(fields=("trade", "position"), name="paper_target_slot_unique"),
            models.CheckConstraint(
                condition=Q(position__gte=1) & Q(position__lte=3),
                name="paper_target_slot_range",
            ),
            models.CheckConstraint(condition=Q(price__gt=0), name="paper_target_price_positive"),
            models.CheckConstraint(
                condition=Q(allocated_quantity__gte=0) & Q(filled_quantity__gte=0),
                name="paper_target_quantities_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(share_percent__gt=0) & Q(share_percent__lte=100),
                name="paper_target_share_valid",
            ),
        ]

    def __str__(self):
        return f"Paper {self.trade_id} TP{self.position} {self.state}"


class TradeProtection(models.Model):
    """Persistent Paper managed SL and trailing rules; never a native exchange stop."""

    class Coverage(models.TextChoices):
        PENDING = "pending", "در انتظار ورود"
        MONITORED = "monitored", "محافظت وابسته به Worker"
        STALE = "stale", "فید قدیمی"
        CANCELLING = "cancelling", "لغو نامشخص"
        CLOSED = "closed", "بسته‌شده"

    trade = models.OneToOneField(Trade, on_delete=models.CASCADE, related_name="protection")
    initial_stop = models.DecimalField(max_digits=32, decimal_places=16)
    effective_stop = models.DecimalField(max_digits=32, decimal_places=16)
    coverage = models.CharField(max_length=16, choices=Coverage.choices, default=Coverage.PENDING)
    step_enabled = models.BooleanField(default=False)
    paper_scenario = models.BooleanField(default=False)
    percentage_enabled = models.BooleanField(default=False)
    percentage_active = models.BooleanField(default=False)
    trigger_price = models.DecimalField(max_digits=32, decimal_places=16)
    distance_percent = models.DecimalField(max_digits=8, decimal_places=4, default=1)
    high_water = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    low_water = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    last_price = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    last_tick_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(initial_stop__gt=0) & Q(effective_stop__gt=0),
                name="paper_protection_positive_stop",
            ),
            models.CheckConstraint(
                condition=Q(distance_percent__gt=0) & Q(distance_percent__lt=100),
                name="paper_trailing_distance_valid",
            ),
        ]

    def __str__(self):
        return f"Paper protection {self.trade_id} {self.coverage}"


class PaperExitFill(models.Model):
    """Durable, uniquely keyed Paper SELL ledger; never submitted to Binance."""

    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name="exit_fills")
    target = models.ForeignKey(
        TradeTarget, on_delete=models.SET_NULL, null=True, blank=True, related_name="fills"
    )
    tick_key = models.CharField(max_length=100)
    reason = models.CharField(max_length=24)
    quantity = models.DecimalField(max_digits=32, decimal_places=16)
    price = models.DecimalField(max_digits=32, decimal_places=16)
    fee = models.DecimalField(max_digits=32, decimal_places=16, default=0)
    fee_asset = models.ForeignKey(
        "exchanges.Asset",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="exit_fee_fills",
    )
    fee_quote_rate = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    occurred_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("trade", "tick_key", "reason", "target"), name="paper_exit_fill_unique_tick"
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="paper_exit_qty_positive"),
        ]

    def __str__(self):
        return f"Paper exit {self.trade_id}: {self.reason}"


class TradeFinanceEvent(models.Model):
    """Provider/reconciliation finance ledger used by reports, never an order instruction."""

    class Kind(models.TextChoices):
        BORROW_INTEREST = "borrow_interest", "بهره وام Margin"
        REPAYMENT = "repayment", "بازپرداخت اصل وام"

    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name="finance_events")
    asset = models.ForeignKey("exchanges.Asset", on_delete=models.PROTECT)
    kind = models.CharField(max_length=24, choices=Kind.choices)
    amount = models.DecimalField(max_digits=32, decimal_places=16)
    quote_rate = models.DecimalField(
        max_digits=32,
        decimal_places=16,
        null=True,
        blank=True,
        help_text="نرخ قطعی دارایی هزینه به ارز quote در زمان رویداد",
    )
    provider_reference = models.CharField(max_length=120)
    occurred_at = models.DateTimeField()

    class Meta:
        ordering = ("occurred_at", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("trade", "provider_reference"),
                name="trade_finance_provider_reference_unique",
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="trade_finance_amount_positive"),
            models.CheckConstraint(
                condition=Q(quote_rate__isnull=True) | Q(quote_rate__gt=0),
                name="trade_finance_quote_rate_positive",
            ),
        ]

    def __str__(self):
        return f"{self.trade_id}:{self.kind}:{self.provider_reference}"


class PaperPriceEvent(models.Model):
    """Idempotent market event ingestion and ordering for recovery."""

    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name="price_events")
    event_key = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=32, decimal_places=16)
    observed_at = models.DateTimeField()
    source = models.CharField(max_length=24, default="simulator")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("trade", "event_key"), name="paper_tick_trade_key_unique"
            ),
            models.CheckConstraint(condition=Q(price__gt=0), name="paper_tick_price_positive"),
        ]

    def __str__(self):
        return f"Paper tick {self.trade_id} {self.event_key}"


class TradeAction(models.Model):
    """Durable, idempotent operator close; committed with its resulting exit ledger."""

    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name="actions")
    request_key = models.UUIDField()
    revision = models.PositiveIntegerField()
    state = models.CharField(
        max_length=16,
        default="pending",
        choices=[
            ("pending", "در صف Worker"),
            ("waiting_feed", "منتظر قیمت معتبر"),
            ("done", "انجام‌شده"),
            ("rejected", "نیازمند بررسی"),
        ],
    )
    code = models.CharField(max_length=48, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    result = models.JSONField(default=dict)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("trade", "request_key"), name="trade_action_request_unique"
            )
        ]
        indexes = [models.Index(fields=("state", "next_attempt_at"))]

    def __str__(self):
        return f"Paper close {self.pk}: {self.state}"
