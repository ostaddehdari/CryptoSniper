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
