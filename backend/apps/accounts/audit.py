import hashlib
import hmac

from django.conf import settings

from .models import AuditLog


def record_audit(event_type, *, request=None, user=None, metadata=None):
    address = request.META.get("REMOTE_ADDR", "") if request else ""
    ip_hash = ""
    if address:
        ip_hash = hmac.new(
            settings.SECRET_KEY.encode(), address.encode(), hashlib.sha256
        ).hexdigest()
    return AuditLog.objects.create(
        owner=user if getattr(user, "is_authenticated", False) else None,
        event_type=event_type,
        metadata=metadata or {},
        ip_hash=ip_hash,
    )
