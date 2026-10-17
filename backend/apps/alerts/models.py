"""Alert events only notify; they cannot submit, cancel or change a trade."""

from django.conf import settings
from django.db import models
from django.db.models import Q


class PriceAlert(models.Model):
    class Kind(models.TextChoices):
        PRICE = "price", "رسیدن به قیمت"
        RISE = "rise", "افزایش درصدی از مبنای ثابت"
        FALL = "fall", "کاهش درصدی از مبنای ثابت"
        PROFIT = "profit", "سود خالص درصدی معامله Paper"
        ENTRY = "entry_change", "تغییر درصد نسبت به Entry"
        SL = "near_sl", "نزدیکی به حد ضرر مؤثر"
        ACTIVATION = "near_activation", "نزدیکی به فعال‌سازی Percentage"
        STOP = "near_stop", "نزدیکی به Percentage Stop فعال"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    market = models.ForeignKey("exchanges.ExchangeMarket", on_delete=models.CASCADE)
    trade = models.ForeignKey("trading.Trade", on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=100)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    direction = models.CharField(
        max_length=8,
        choices=[("above", "بالاتر یا مساوی"), ("below", "پایین‌تر یا مساوی")],
        default="above",
    )
    threshold = models.DecimalField(max_digits=32, decimal_places=16)
    reference_price = models.DecimalField(max_digits=32, decimal_places=16)
    reference_at = models.DateTimeField()
    reference_source = models.CharField(max_length=30)
    repeat = models.BooleanField(default=False)
    hysteresis = models.DecimalField(max_digits=8, decimal_places=4, default="0.1")
    cooldown_seconds = models.PositiveIntegerField(default=60)
    enabled = models.BooleanField(default=True)
    status = models.CharField(max_length=24, default="watching")
    armed = models.BooleanField(default=True)
    last_metric = models.DecimalField(max_digits=32, decimal_places=16, null=True)
    last_observed_at = models.DateTimeField(null=True)
    last_fired_at = models.DateTimeField(null=True)
    fire_count = models.PositiveIntegerField(default=0)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=("enabled", "market")),
            models.Index(fields=("owner", "-created_at")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(reference_price__gt=0), name="alert_reference_positive"
            ),
            models.CheckConstraint(
                condition=Q(hysteresis__gte=0) & Q(hysteresis__lte=20),
                name="alert_hysteresis_range",
            ),
            models.CheckConstraint(
                condition=Q(cooldown_seconds__gte=5) & Q(cooldown_seconds__lte=86400),
                name="alert_cooldown_range",
            ),
        ]

    def __str__(self):
        return self.title


class NotificationPreference(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    in_app = models.BooleanField(default=True)
    browser = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification preferences {self.owner_id}"


class AlertEvent(models.Model):
    alert = models.ForeignKey(PriceAlert, on_delete=models.CASCADE, related_name="events")
    sequence = models.PositiveIntegerField()
    observed_at = models.DateTimeField()
    price = models.DecimalField(max_digits=32, decimal_places=16)
    metric = models.DecimalField(max_digits=32, decimal_places=16)
    basis = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("alert", "sequence"), name="alert_event_sequence_unique"
            )
        ]

    def __str__(self):
        return f"Alert {self.alert_id} #{self.sequence}"


class Notification(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    event = models.OneToOneField(AlertEvent, on_delete=models.CASCADE)
    title = models.CharField(max_length=160)
    body = models.TextField()
    severity = models.CharField(max_length=12, default="info")
    in_app = models.BooleanField(default=True)
    browser = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True)
    browser_delivered_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-pk",)

    def __str__(self):
        return self.title
