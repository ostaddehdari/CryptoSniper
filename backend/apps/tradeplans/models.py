import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class TradePlan(models.Model):
    """Owner-controlled paper-only intent. Absolutely no exchange order is placed."""

    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        READY = "ready", "تأییدشده برای بررسی"

    class Side(models.TextChoices):
        LONG = "long", "خرید / Long"
        SHORT = "short", "فروش / Short"

    class TrailingTrigger(models.TextChoices):
        TP1 = "tp1", "TP1"
        TP2 = "tp2", "TP2"
        TP3 = "tp3", "TP3"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trade_plans"
    )
    exchange_account = models.ForeignKey("exchanges.UserExchangeAccount", on_delete=models.CASCADE)
    market = models.ForeignKey("exchanges.ExchangeMarket", on_delete=models.PROTECT)
    client_token = models.UUIDField(default=uuid.uuid4)
    source = models.CharField(max_length=24, default="manual")
    origin_signal = models.ForeignKey(
        "signals.Signal", on_delete=models.CASCADE, null=True, blank=True
    )
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    side = models.CharField(max_length=8, choices=Side.choices, default=Side.LONG)
    entry_price = models.DecimalField(max_digits=32, decimal_places=16)
    stop_loss = models.DecimalField(max_digits=32, decimal_places=16)
    tp1 = models.DecimalField(max_digits=32, decimal_places=16)
    tp2 = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    tp3 = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    capital = models.DecimalField(
        max_digits=32, decimal_places=16, validators=[MinValueValidator(Decimal("0.00000001"))]
    )
    leverage = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal("1"))
    trailing_sl = models.BooleanField(default=False)
    percentage_trailing = models.BooleanField(default=False)
    trailing_trigger = models.CharField(
        max_length=3, choices=TrailingTrigger.choices, default=TrailingTrigger.TP1
    )
    trailing_distance = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("1"))
    preview = models.JSONField(default=dict)
    approved_snapshot = models.JSONField(default=dict, blank=True)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "client_token"), name="tradeplan_owner_token_unique"
            ),
            models.CheckConstraint(condition=Q(capital__gt=0), name="tradeplan_capital_positive"),
            models.CheckConstraint(
                condition=Q(leverage__gte=1), name="tradeplan_leverage_positive"
            ),
        ]

    def __str__(self):
        return f"Plan #{self.pk} for {self.owner_id} ({self.status})"
