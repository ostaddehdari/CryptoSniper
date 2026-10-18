"""Retention boundaries for security records and ephemeral private data."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import AuditLog, PasswordResetRequest, UserSession


def retained_audit_events(user, *, now=None):
    now = now or timezone.now()
    cutoff = now - timedelta(days=settings.AUDIT_RETENTION_DAYS)
    return AuditLog.objects.filter(owner=user, created_at__gte=cutoff)


def minimize_expired_security_data(*, now=None):
    """Remove ephemeral identifiers; append-only audit rows stay immutable."""

    now = now or timezone.now()
    resets, _ = PasswordResetRequest.objects.filter(
        expires_at__lt=now - timedelta(days=7)
    ).delete()
    sessions, _ = UserSession.objects.filter(
        revoked_at__isnull=False, revoked_at__lt=now - timedelta(days=30)
    ).delete()
    return {"password_resets": resets, "sessions": sessions}
