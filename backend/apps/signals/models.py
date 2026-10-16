"""The three canonical signal ingress methods, no Telegram or AI adapter in S06."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class SignalSource(models.Model):
    class Method(models.TextChoices):
        MANUAL = "manual", "ورود دستی"
        SMART_PASTE = "smart_paste", "چسباندن هوشمند"
        TELEGRAM = "telegram", "تلگرام (فقط Stage21)"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name="signal_sources")
    name = models.CharField(max_length=80)
    method = models.CharField(max_length=16, choices=Method.choices)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("method", "name", "pk")
        constraints = [
            models.UniqueConstraint(fields=("owner", "method", "name"),
                                    name="signal_source_owner_method_name_unique")
        ]

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": "نام منبع لازم است."})

    def __str__(self):
        return f"{self.name} ({self.method})"


class RawSignal(models.Model):
    """Immutable original input. New versions are append-only RawSignalRevision rows."""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name="raw_signals")
    source = models.ForeignKey(SignalSource, on_delete=models.PROTECT, related_name="inputs")
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
            models.UniqueConstraint(fields=("owner", "source", "checksum"),
                                    name="rawsignal_owner_source_checksum_unique"),
            models.UniqueConstraint(fields=("owner", "source", "external_id"),
                                    condition=~models.Q(external_id=""),
                                    name="rawsignal_owner_source_external_unique"),
        ]
        indexes = [models.Index(fields=("owner", "received_at"))]

    def __str__(self):
        return f"Raw #{self.pk} · {self.source_id} · r{self.revision_number}"


class RawSignalRevision(models.Model):
    raw_signal = models.ForeignKey(RawSignal, on_delete=models.CASCADE,
                                   related_name="revisions")
    version = models.PositiveIntegerField()
    text = models.TextField()
    payload = models.JSONField(default=dict)
    checksum = models.CharField(max_length=64)
    received_version = models.CharField(max_length=24, default="v1")
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("version",)
        constraints = [
            models.UniqueConstraint(fields=("raw_signal", "version"),
                                    name="rawsignal_revision_unique"),
        ]

    def __str__(self):
        return f"Raw #{self.raw_signal_id} revision {self.version}"
