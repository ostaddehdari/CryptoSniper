from django.conf import settings
from django.db import models


class PerformanceAggregate(models.Model):
    """Replace-in-place owner aggregate; source rows remain the authoritative ledger."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="performance_aggregates"
    )
    timezone = models.CharField(max_length=64)
    period_kind = models.CharField(
        max_length=8, choices=[("day", "روز"), ("week", "هفته"), ("month", "ماه")]
    )
    period_start = models.DateField()
    dimension_kind = models.CharField(
        max_length=12,
        choices=[
            ("total", "همه"),
            ("coin", "ارز"),
            ("exchange", "صرافی"),
            ("source", "منبع"),
        ],
    )
    dimension_value = models.CharField(max_length=80)
    mode = models.CharField(max_length=12)
    currency = models.CharField(max_length=20)
    trade_count = models.PositiveIntegerField(default=0)
    unknown_count = models.PositiveIntegerField(default=0)
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    breakeven = models.PositiveIntegerField(default=0)
    gross_realized = models.DecimalField(max_digits=40, decimal_places=16, default=0)
    net_realized = models.DecimalField(max_digits=40, decimal_places=16, default=0)
    fees = models.DecimalField(max_digits=40, decimal_places=16, default=0)
    margin_interest = models.DecimalField(max_digits=40, decimal_places=16, default=0)
    duration_seconds = models.PositiveBigIntegerField(default=0)
    source_fingerprint = models.CharField(max_length=64)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("period_start", "dimension_kind", "dimension_value")
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "owner",
                    "timezone",
                    "period_kind",
                    "period_start",
                    "dimension_kind",
                    "dimension_value",
                    "mode",
                    "currency",
                ),
                name="report_aggregate_identity_unique",
            )
        ]
        indexes = [
            models.Index(fields=("owner", "period_kind", "period_start")),
            models.Index(fields=("owner", "dimension_kind", "dimension_value")),
        ]

    def __str__(self):
        return f"{self.owner_id}:{self.period_kind}:{self.period_start}:{self.dimension_value}"
