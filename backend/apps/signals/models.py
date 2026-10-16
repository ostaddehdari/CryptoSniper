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
