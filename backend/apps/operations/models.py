"""Durable operational state. No control grants permission to trade live."""

from django.db import models


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
    observed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("account", "kind", "external_id"), name="external_observation_unique"
            )
        ]

    def __str__(self):
        return f"External {self.kind}: {self.external_id}"


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



class ExternalTradeManagement(models.Model):
    """Explicitly adopted LIVE Spot position management.

    Nothing is adopted automatically. The operator configures the rule and the
    trailing worker may create at most one durable LiveSpotOrder exit.
    """

    class State(models.TextChoices):
        ACTIVE = "active", "فعال"
        PAUSED = "paused", "متوقف"
        EXITING = "exiting", "در حال خروج"
        CLOSED = "closed", "بسته"
        ERROR = "error", "خطا"

    observation = models.OneToOneField(
        ExternalObservation,
        on_delete=models.PROTECT,
        related_name="management",
    )
    owner = models.ForeignKey("accounts.User", on_delete=models.CASCADE)
    account = models.ForeignKey("exchanges.UserExchangeAccount", on_delete=models.PROTECT)
    market = models.ForeignKey("exchanges.ExchangeMarket", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=32, decimal_places=16)
    entry_price = models.DecimalField(max_digits=32, decimal_places=16)
    stop_loss = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    tp1 = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    tp2 = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    tp3 = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    trailing_enabled = models.BooleanField(default=False)
    trailing_sl_enabled = models.BooleanField(default=False)
    trailing_trigger = models.CharField(
        max_length=8,
        choices=(("tp1", "TP1"), ("tp2", "TP2"), ("tp3", "TP3")),
        default="tp1",
    )
    trailing_distance_percent = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=1,
    )
    high_water = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    effective_stop = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    breakeven_moved = models.BooleanField(default=False)
    last_price = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    last_tick_at = models.DateTimeField(null=True, blank=True)
    exit_order = models.OneToOneField(
        "exchanges.LiveSpotOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="external_management",
    )
    state = models.CharField(max_length=12, choices=State.choices, default=State.ACTIVE)
    last_error = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-pk")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="external_management_quantity_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(entry_price__gt=0),
                name="external_management_entry_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(trailing_distance_percent__gt=0)
                & models.Q(trailing_distance_percent__lt=100),
                name="external_management_trailing_distance_range",
            ),
        ]

    def __str__(self):
        return f"External management {self.pk} [{self.state}]"
