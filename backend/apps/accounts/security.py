import hashlib
import logging
from datetime import datetime, timedelta
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone

logger = logging.getLogger(__name__)
STEP_UP_SESSION_KEY = "security_step_up_at"


def _login_key(request, username):
    identity = f"{request.META.get('REMOTE_ADDR', '')}|{username.strip().casefold()}"
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return f"auth:login-failures:{digest}"


def login_attempts(request, username):
    try:
        return int(cache.get(_login_key(request, username), 0))
    except Exception:
        logger.warning("Login rate-limit cache unavailable")
        return 0


def record_login_failure(request, username):
    key = _login_key(request, username)
    try:
        cache.add(key, 0, timeout=settings.AUTH_LOGIN_WINDOW_SECONDS)
        return int(cache.incr(key))
    except Exception:
        logger.warning("Could not update login rate limit")
        return 0


def clear_login_failures(request, username):
    try:
        cache.delete(_login_key(request, username))
    except Exception:
        logger.warning("Could not clear login rate limit")


def session_api_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "authentication_required"}, status=401)
        if request.user.account_status != "active":
            return JsonResponse({"error": "account_unavailable"}, status=403)
        return view(request, *args, **kwargs)

    return wrapped


def mark_step_up(request):
    request.session.cycle_key()
    request.session[STEP_UP_SESSION_KEY] = timezone.now().isoformat()


def has_recent_step_up(request):
    raw = request.session.get(STEP_UP_SESSION_KEY)
    if not raw:
        return False
    try:
        happened = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return False
    if timezone.is_naive(happened):
        happened = timezone.make_aware(happened)
    return timezone.now() - happened <= timedelta(minutes=10)


def step_up_required(view):
    """Require recent password verification for a destructive credential action."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "authentication_required"}, status=401)
        if not has_recent_step_up(request):
            return JsonResponse(
                {
                    "error": "step_up_required",
                    "verify_url": "/settings/security/step-up/",
                },
                status=403,
            )
        return view(request, *args, **kwargs)

    return wrapped


def second_factor_status():
    """Capability status, not a pretend 2FA implementation."""

    provider = getattr(settings, "SECOND_FACTOR_PROVIDER", "")
    return {
        "configured": bool(provider),
        "provider": provider or None,
        "live_ready": bool(provider) and bool(settings.LIVE_TRADING_ENABLED),
        "message": (
            "ارائه‌دهنده مرحله دوم پیکربندی شده است."
            if provider
            else "ارائه‌دهنده 2FA هنوز انتخاب نشده؛ اجرای Live غیرفعال است."
        ),
    }
