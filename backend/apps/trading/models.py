"""Stage 08: durable paper-only lifecycle. Production exchange orders are disabled."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Trade(models.Model):
    class State(models.TextChoices):
        QUEUED = "queued", "در صف"
        SUBMITTING = "submitting", "در حال ارسال شبیه‌ساز"
        PARTIAL = "partially_filled", "بخشی اجرا شده"
        OPEN = "open", "باز"
        UNCERTAIN = "uncertain", "نتیجه نامعلوم"
        FAILED = "failed", "ناموفق"
        CANCELLED = "cancelled", "لغوشده"

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
