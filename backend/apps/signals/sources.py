"""Versioned ingestion contract shared by local and final-stage Telegram sources."""

from dataclasses import dataclass
from typing import Protocol

from django.core.exceptions import ValidationError

from .models import SignalSource


@dataclass(frozen=True)
class InboundEnvelope:
    """Raw input belongs to an explicitly owner-scoped source."""

    text: str
    payload: dict
    external_id: str = ""
    received_version: str = "v1"


class SourceTransport(Protocol):
    def read(self) -> InboundEnvelope:
        """Future interface only; Stage 06 does not instantiate providers."""


def get_default_source(user, method=SignalSource.Method.MANUAL):
    if method not in {SignalSource.Method.MANUAL, SignalSource.Method.SMART_PASTE}:
        raise ValidationError("اتصال خارجی تا استیج ۲۱ غیرفعال است.")
    name = {
        SignalSource.Method.MANUAL: "ورود دستی من",
        SignalSource.Method.SMART_PASTE: "Smart Paste من",
    }[method]
    source, _ = SignalSource.objects.get_or_create(owner=user, name=name, method=method)
    return source


def ensure_ingress_allowed(source):
    if not source.enabled:
        raise ValidationError("این منبع غیرفعال است.")
