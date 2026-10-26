"""Durable operational state. Live control remains explicit and fail-closed."""

import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q


class AccountControl(models.Model):
    account = models.OneToOneField("exchanges.UserExchangeAccount", on_delete=models.CASCADE)
    paused = models.BooleanField(default=False)
    reason = models.CharField(max_length=80, blank=True)
    version = models.PositiveIntegerField(default=1)
    last_reconciled_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Account {self.account_id} paused={self.paused}"


class RecoveryIssue(models.Model):
    account = models.ForeignKey("exchanges.UserExchangeAccount", on_delete=models.CASCADE)
    key = models.CharField(max_length=100)
    code = models.CharField(max_length=50)
    detail = models.JSONField(default=dict)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("account", "key"), name="recovery_key_unique")
        ]

    def __str__(self):
        return f"Recovery {self.account_id}: {self.code}"


class WorkerHeartbeat(models.Model):
    queue = models.CharField(max_length=24, unique=True)
    seen_at = models.DateTimeField()
    worker = models.CharField(max_length=100)
    lag_seconds = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.queue


class ExternalObservation(models.Model):
    """Read-only provider observations; never converted into managed trades."""

    account = models.ForeignKey("exchanges.UserExchangeAccount", on_delete=models.CASCADE)
    external_id = models.CharField(max_length=120)
    kind = models.CharField(max_length=16)
    payload = models.JSONField(default=dict)
    archived_at = models.DateTimeField(null=True, blank=True)
    observed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("account", "kind", "external_id"), name="external_observation_unique"
            )
        ]

    def __str__(self):
        return f"External {self.kind}: {self.external_id}"


class ExternalTradePolicy(models.Model):
    """Explicit user-confirmed management of an observed external Spot long."""

    class State(models.TextChoices):
        ACTIVE = "active", "فعال"
        EXIT_SUBMITTED = "exit_submitted", "خروج ارسال شده"
        DISABLED = "disabled", "غیرفعال"
        ERROR = "error", "خطا"

    observation = models.OneToOneField(
        ExternalObservation, on_delete=models.CASCADE, related_name="management_policy"
    )
    market = models.ForeignKey("exchanges.ExchangeMarket", on_delete=models.PROTECT)
    entry_price = models.DecimalField(max_digits=32, decimal_places=16)
    remaining_amount = models.DecimalField(max_digits=32, decimal_places=16)
    stop_loss = models.DecimalField(max_digits=32, decimal_places=16)
    tp1 = models.DecimalField(max_digits=32, decimal_places=16)
    tp2 = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    tp3 = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    trailing_enabled = models.BooleanField(default=True)
    trailing_sl_enabled = models.BooleanField(default=True)
    trailing_trigger = models.PositiveSmallIntegerField(default=1)
    trailing_distance_percent = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("1")
    )
    effective_stop = models.DecimalField(max_digits=32, decimal_places=16)
    trailing_active = models.BooleanField(default=False)
    high_water = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    state = models.CharField(max_length=20, choices=State.choices, default=State.ACTIVE)
    exit_request_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    exit_order = models.ForeignKey(
        "exchanges.LiveSpotOrder", on_delete=models.SET_NULL, null=True, blank=True
    )
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(entry_price__gt=0)
                & Q(remaining_amount__gt=0)
                & Q(stop_loss__gt=0)
                & Q(tp1__gt=0),
                name="external_policy_positive_core_values",
            ),
            models.CheckConstraint(
                condition=Q(trailing_trigger__gte=1) & Q(trailing_trigger__lte=3),
                name="external_policy_trigger_range",
            ),
            models.CheckConstraint(
                condition=Q(trailing_distance_percent__gt=0) & Q(trailing_distance_percent__lt=100),
                name="external_policy_distance_range",
            ),
        ]

    def __str__(self):
        return f"External policy {self.observation_id} ({self.state})"


class PaperProviderOrder(models.Model):
    """Independent, durable Paper provider receipt survives executor process loss."""

    account = models.ForeignKey("exchanges.UserExchangeAccount", on_delete=models.CASCADE)
    client_order_id = models.CharField(max_length=80)
    external_order_id = models.CharField(max_length=100, unique=True)
    symbol = models.CharField(max_length=32)
    quantity = models.DecimalField(max_digits=32, decimal_places=16)
    price = models.DecimalField(max_digits=32, decimal_places=16)
    fee = models.DecimalField(max_digits=32, decimal_places=16)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("account", "client_order_id"), name="paper_provider_client_unique"
            )
        ]

    def __str__(self):
        return self.client_order_id


class ManagedSpotPosition(models.Model):
    """An explicitly authorized Spot-long inventory; order receipts are cumulative evidence."""

    account = models.ForeignKey("exchanges.UserExchangeAccount", on_delete=models.PROTECT)
    market = models.ForeignKey("exchanges.ExchangeMarket", on_delete=models.PROTECT)
    entry_order = models.OneToOneField(
        "exchanges.LiveSpotOrder",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="entry_position",
    )
    external_policy = models.OneToOneField(
        ExternalTradePolicy,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="managed_position",
    )
    snapshot = models.JSONField(default=dict)
    acquired = models.DecimalField(max_digits=32, decimal_places=16, default=0)
    exited = models.DecimalField(max_digits=32, decimal_places=16, default=0)
    effective_stop = models.DecimalField(max_digits=32, decimal_places=16)
    high_water = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    break_even_applied = models.BooleanField(default=False)
    trailing_active = models.BooleanField(default=False)
    paused = models.BooleanField(default=False)
    state = models.CharField(max_length=24, default="waiting_entry")
    exit_latched = models.BooleanField(default=False)
    exit_sequence = models.PositiveIntegerField(default=0)
    version = models.PositiveIntegerField(default=1)
    error_code = models.CharField(max_length=60, blank=True)
    last_price = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    last_price_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(entry_order__isnull=False, external_policy__isnull=True)
                    | Q(entry_order__isnull=True, external_policy__isnull=False)
                ),
                name="managed_spot_one_source",
            ),
            models.CheckConstraint(
                condition=Q(acquired__gte=0)
                & Q(exited__gte=0)
                & Q(exited__lte=models.F("acquired")),
                name="managed_spot_inventory_valid",
            ),
        ]

    def __str__(self):
        return f"Managed Spot {self.pk} ({self.state})"

    @property
    def remaining(self):
        return self.acquired - self.exited


class LiveExitAttempt(models.Model):
    position = models.ForeignKey(
        ManagedSpotPosition, on_delete=models.PROTECT, related_name="exits"
    )
    order = models.OneToOneField(
        "exchanges.LiveSpotOrder", on_delete=models.PROTECT, related_name="managed_exit"
    )
    sequence = models.PositiveIntegerField()
    reason = models.CharField(max_length=16)
    trigger_price = models.DecimalField(max_digits=32, decimal_places=16)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("position", "sequence"), name="live_exit_sequence_unique"
            )
        ]

    def __str__(self):
        return f"Exit {self.position_id}:{self.sequence} ({self.reason})"
