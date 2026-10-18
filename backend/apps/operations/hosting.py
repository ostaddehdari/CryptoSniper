"""Measured hosting capabilities without overstating unavailable infrastructure."""

import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.db import connections
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from redis.exceptions import RedisError

from apps.core.health import dependency_status
from apps.core.security import validate_public_https_url

from .models import WorkerHeartbeat


def _row(key, label, ok, evidence, *, required=True):
    return {
        "key": key,
        "label": label,
        "ok": bool(ok),
        "required": required,
        "evidence": evidence,
    }


def _storage_writable():
    target = Path(settings.HOSTING_BACKUP_DIR)
    try:
        target.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".capability-", dir=target, delete=True):
            return True
    except OSError:
        return False


def _outbound_https(timeout=3):
    url = settings.HOSTING_EGRESS_PROBE_URL
    validate_public_https_url(url)
    try:
        with urlopen(Request(url, method="HEAD"), timeout=timeout) as response:  # noqa: S310
            return 200 <= response.status < 500
    except (OSError, URLError):
        return False


def _scheduler_fresh():
    try:
        payload = cache.get("worker_heartbeat")
    except RedisError:
        return False
    seen = parse_datetime(payload.get("seen_at", "")) if isinstance(payload, dict) else None
    return bool(seen and timezone.now() - seen < timedelta(seconds=95))


def _worker_coverage():
    cutoff = timezone.now() - timedelta(seconds=95)
    fresh = set(WorkerHeartbeat.objects.filter(seen_at__gte=cutoff).values_list("queue", flat=True))
    required = set(settings.OPERATION_QUEUES)
    return fresh, required


def hosting_capabilities(*, probe_outbound=False, probe_storage=False):
    dependencies = dependency_status()
    fresh, queues = _worker_coverage()
    storage_ok = _storage_writable() if probe_storage else None
    outbound_ok = _outbound_https() if probe_outbound else None
    python_ok = sys.version_info >= (3, 12)
    postgresql = connections["default"].vendor == "postgresql" and dependencies["postgresql"]
    rows = [
        _row("python", "Python 3.12+", python_ok, sys.version.split()[0]),
        _row("postgresql", "PostgreSQL", postgresql, "connected" if postgresql else "unavailable"),
        _row(
            "redis",
            "Redis cache/broker/results",
            all(
                dependencies.get(k, False) for k in ("redis_cache", "redis_broker", "redis_results")
            ),
            "three roles checked",
        ),
        _row(
            "outbound_https",
            "Outbound HTTPS",
            outbound_ok,
            "measured" if probe_outbound else "not measured; run --probe-outbound",
        ),
        _row(
            "workers",
            "Persistent workers",
            queues <= fresh,
            f"fresh {len(fresh)}/{len(queues)} queues",
        ),
        _row(
            "scheduler",
            "Single leased scheduler",
            _scheduler_fresh(),
            "fresh Beat receipt required",
        ),
        _row(
            "https",
            "HTTPS production policy",
            bool(getattr(settings, "SECURE_SSL_REDIRECT", False)),
            "secure redirect and secure cookies",
        ),
        _row(
            "storage",
            "Persistent backup storage",
            storage_ok,
            "measured" if probe_storage else "not measured; run --probe-storage",
        ),
        _row("wsgi", "WSGI", bool(settings.WSGI_APPLICATION), settings.WSGI_APPLICATION),
        _row("asgi", "ASGI", bool(settings.ASGI_APPLICATION), settings.ASGI_APPLICATION),
        _row(
            "node",
            "Node runtime",
            True,
            "not required at runtime",
            required=False,
        ),
    ]
    required = [row for row in rows if row["required"]]
    return {
        "status": "ready" if required and all(row["ok"] for row in required) else "incomplete",
        "environment": os.environ.get("DJANGO_SETTINGS_MODULE", "unknown").rsplit(".", 1)[-1],
        "capabilities": rows,
        "missing": [row["key"] for row in required if not row["ok"]],
        "telegram_listener": "reserved_for_stage21_not_running",
    }
