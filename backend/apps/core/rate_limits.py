"""Central request limits for browser/API surfaces; financial writes fail closed."""

import hashlib
import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse

logger = logging.getLogger(__name__)


class RequestLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        length = request.META.get("CONTENT_LENGTH", "")
        try:
            if length and int(length) > settings.REQUEST_BODY_MAX_BYTES:
                return JsonResponse({"error": "payload_too_large"}, status=413)
        except ValueError:
            return JsonResponse({"error": "invalid_content_length"}, status=400)
        policy = self._policy(request)
        if policy:
            response = self._consume(request, *policy)
            if response:
                return response
        return self.get_response(request)

    @staticmethod
    def _policy(request):
        path = request.path_info
        if path in {"/api/v1/smart-paste/", "/api/v1/inbox/receive/"}:
            return "parser", settings.PARSER_RATE_LIMIT_PER_MINUTE
        if path == "/api/v1/markets/stream/":
            return "subscription", settings.SUBSCRIPTION_RATE_LIMIT_PER_MINUTE
        if path.startswith("/api/"):
            return "api", settings.API_RATE_LIMIT_PER_MINUTE
        return None

    @staticmethod
    def _consume(request, bucket, limit):
        identity = (
            f"user:{request.user.pk}"
            if getattr(request.user, "is_authenticated", False)
            else f"ip:{request.META.get('REMOTE_ADDR', '')}"
        )
        minute = int(time.time() // 60)
        digest = hashlib.sha256(identity.encode()).hexdigest()
        key = f"request-limit:{bucket}:{minute}:{digest}"
        try:
            cache.add(key, 0, timeout=75)
            count = cache.incr(key)
        except Exception:
            logger.error("Request rate-limit storage unavailable", extra={"bucket": bucket})
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                return JsonResponse({"error": "security_limit_unavailable"}, status=503)
            return None
        if count <= limit:
            return None
        response = JsonResponse({"error": "rate_limited", "bucket": bucket}, status=429)
        response["Retry-After"] = "60"
        return response
