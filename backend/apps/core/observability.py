import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from uuid import UUID, uuid4

from django.conf import settings

correlation_id = ContextVar("correlation_id", default="-")


class CorrelationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            value = str(UUID(request.headers.get("X-Correlation-ID", "")))
        except (ValueError, TypeError):
            value = str(uuid4())
        request.correlation_id = value
        token = correlation_id.set(value)
        try:
            response = self.get_response(request)
            response["X-Correlation-ID"] = value
            return response
        finally:
            correlation_id.reset(token)


class RedactingJsonFormatter(logging.Formatter):
    def format(self, record):
        message = record.getMessage()
        if record.exc_info:
            message += " " + self.formatException(record.exc_info)
        message = re.sub(r"(\w+://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", message)
        message = re.sub(
            r"(?i)((?:api_?key|secret|password|token|authorization)\s*[=:]\s*)[^\s,;]+",
            r"\1[REDACTED]",
            message,
        )
        message = message.replace(settings.SECRET_KEY, "[REDACTED]")
        return json.dumps(
            {
                "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "correlation_id": correlation_id.get(),
                "message": message,
            },
            ensure_ascii=False,
        )
