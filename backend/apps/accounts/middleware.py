from datetime import timedelta

from django.contrib.auth import logout
from django.utils import timezone

from .models import UserSession


class SessionTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            self._reject_revoked_or_disabled(request)
        response = self.get_response(request)
        if request.user.is_authenticated:
            self._track(request)
        return response

    @staticmethod
    def _reject_revoked_or_disabled(request):
        key = request.session.session_key
        tracked = (
            UserSession.objects.filter(session_key=key).only("revoked_at", "expires_at").first()
        )
        if request.user.account_status != "active" or (
            tracked and (tracked.revoked_at or tracked.expires_at <= timezone.now())
        ):
            logout(request)

    @staticmethod
    def _track(request):
        if not request.session.session_key:
            request.session.save()
        key = request.session.session_key
        now = timezone.now()
        defaults = {
            "owner": request.user,
            "user_agent_label": request.META.get("HTTP_USER_AGENT", "")[:120],
            "expires_at": request.session.get_expiry_date(),
        }
        tracked, created = UserSession.objects.get_or_create(session_key=key, defaults=defaults)
        if tracked.owner_id != request.user.pk:
            logout(request)
            return
        if not created and tracked.last_seen_at < now - timedelta(minutes=5):
            tracked.last_seen_at = now
            tracked.expires_at = request.session.get_expiry_date()
            tracked.save(update_fields=("last_seen_at", "expires_at"))
