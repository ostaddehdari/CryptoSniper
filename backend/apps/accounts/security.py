import hashlib
import logging
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse

logger = logging.getLogger(__name__)


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
