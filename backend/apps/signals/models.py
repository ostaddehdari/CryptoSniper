"""The three canonical signal ingress methods, no Telegram or AI adapter in S06."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class SignalSource(models.Model):
    class Method(models.TextChoices):
        MANUAL = "manual", "ورود دستی"
        SMART_PASTE = "smart_paste", "چسباندن هوشمند"
        TELEGRAM = "telegram", "تلگرام (فقط Stage21)"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="signal_sources"
    )
    name = models.CharField(max_length=80)
    method = models.CharField(max_length=16, choices=Method.choices)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("method", "name", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "method", "name"), name="signal_source_owner_method_name_unique"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.method})"

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": "نام منبع لازم است."})


class RawSignal(models.Model):
    """Immutable original input. New versions are append-only RawSignalRevision rows."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="raw_signals"
    )
    source = models.ForeignKey(SignalSource, on_delete=models.CASCADE, related_name="inputs")
    original_text = models.TextField()
    original_payload = models.JSONField(default=dict)
    checksum = models.CharField(max_length=64)
    external_id = models.CharField(max_length=160, blank=True)
    received_version = models.CharField(max_length=24, default="v1")
    revision_number = models.PositiveIntegerField(default=1)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-received_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "source", "checksum"),
                name="rawsignal_owner_source_checksum_unique",
            ),
            models.UniqueConstraint(
                fields=("owner", "source", "external_id"),
                condition=~models.Q(external_id=""),
                name="rawsignal_owner_source_external_unique",
            ),
        ]
        indexes = [models.Index(fields=("owner", "received_at"))]

    def __str__(self):
        return f"Raw #{self.pk} · {self.source_id} · r{self.revision_number}"


class RawSignalRevision(models.Model):
    raw_signal = models.ForeignKey(RawSignal, on_delete=models.CASCADE, related_name="revisions")
    version = models.PositiveIntegerField()
    text = models.TextField()
    payload = models.JSONField(default=dict)
    checksum = models.CharField(max_length=64)
    received_version = models.CharField(max_length=24, default="v1")
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("version",)
        constraints = [
            models.UniqueConstraint(
                fields=("raw_signal", "version"), name="rawsignal_revision_unique"
            ),
        ]

    def __str__(self):
        return f"Raw #{self.raw_signal_id} revision {self.version}"


class Signal(models.Model):
    """One entry, at most three executable targets; trade execution is a later stage."""

    class Status(models.TextChoices):
        NEW = "new", "جدید"
        PARSED = "parsed", "ساختارمند"
        NEEDS_REVIEW = "needs_review", "نیازمند بررسی"
        APPROVED = "approved", "تأییدشده"
        REJECTED = "rejected", "ردشده"
        EXECUTED = "executed", "اجراشده"
        FAILED = "failed", "ناموفق"

    class Side(models.TextChoices):
        LONG = "long", "Long"
        SHORT = "short", "Short"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="inbox_signals"
    )
    source = models.ForeignKey(SignalSource, on_delete=models.CASCADE, related_name="signals")
    raw_signal = models.OneToOneField(
        RawSignal, on_delete=models.CASCADE, related_name="structured_signal"
    )
    exchange_account = models.ForeignKey(
        "exchanges.UserExchangeAccount", on_delete=models.CASCADE, null=True, blank=True
    )
    market = models.ForeignKey(
        "exchanges.ExchangeMarket", on_delete=models.PROTECT, null=True, blank=True
    )
    side = models.CharField(max_length=8, choices=Side.choices, blank=True)
    entry_price = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    stop_loss = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    technical_confidence = models.PositiveSmallIntegerField(default=0)
    parser_version = models.CharField(max_length=40, default="manual-v1")
    parsed_payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    review_reason = models.CharField(max_length=500, blank=True)
    revision = models.PositiveIntegerField(default=1)
    approved_snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("owner", "status", "created_at")),
            models.Index(fields=("owner", "source", "created_at")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(technical_confidence__lte=100), name="signal_confidence_lte_100"
            ),
        ]

    def __str__(self):
        return f"Signal #{self.pk} · {self.status}"

    def clean(self):
        super().clean()
        if self.source_id and self.owner_id and self.source.owner_id != self.owner_id:
            raise ValidationError("منبع سیگنال متعلق به این کاربر نیست.")
        if self.raw_signal_id and self.owner_id:
            if (
                self.raw_signal.owner_id != self.owner_id
                or self.raw_signal.source_id != self.source_id
            ):
                raise ValidationError("ورودی اصلی سیگنال با کاربر یا منبع هم‌خوان نیست.")
        if self.market_id and self.exchange_account_id:
            if self.market.exchange_id != self.exchange_account.exchange_id:
                raise ValidationError("بازار متعلق به این اتصال نیست.")
            if self.exchange_account.owner_id != self.owner_id:
                raise ValidationError("حساب صرافی متعلق به کاربر دیگری است.")


class SignalTarget(models.Model):
    signal = models.ForeignKey(Signal, on_delete=models.CASCADE, related_name="targets")
    position = models.PositiveSmallIntegerField()
    price = models.DecimalField(max_digits=32, decimal_places=16)
    share_percent = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        ordering = ("position",)
        constraints = [
            models.UniqueConstraint(
                fields=("signal", "position"), name="signal_target_position_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(position__gte=1) & models.Q(position__lte=3),
                name="signal_target_position_range",
            ),
            models.CheckConstraint(
                condition=models.Q(price__gt=0), name="signal_target_positive_price"
            ),
            models.CheckConstraint(
                condition=models.Q(share_percent__gt=0) & models.Q(share_percent__lte=100),
                name="signal_target_share_range",
            ),
        ]

    def __str__(self):
        return f"Signal {self.signal_id} TP{self.position}"


class SignalRevision(models.Model):
    """Historical structured snapshots; never updated after creation."""

    signal = models.ForeignKey(Signal, on_delete=models.CASCADE, related_name="history")
    revision = models.PositiveIntegerField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    reason = models.CharField(max_length=500)
    snapshot = models.JSONField(default=dict)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("revision",)
        constraints = [
            models.UniqueConstraint(fields=("signal", "revision"), name="signal_revision_unique")
        ]

    def __str__(self):
        return f"Signal {self.signal_id} revision {self.revision}"
