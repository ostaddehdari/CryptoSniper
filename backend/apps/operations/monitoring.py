"""Small, bounded operational snapshot for UI, API and external monitors."""

from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from redis import Redis
from redis.exceptions import RedisError

from apps.exchanges.models import UserExchangeAccount
from apps.trading.models import ExecutionOutbox, TradeProtection

from .models import WorkerHeartbeat


def _queue_depths():
    try:
        with Redis.from_url(
            settings.CELERY_BROKER_URL, socket_connect_timeout=1, socket_timeout=1
        ) as broker:
            return {queue: int(broker.llen(queue)) for queue in settings.OPERATION_QUEUES}
    except RedisError:
        return {queue: None for queue in settings.OPERATION_QUEUES}


def service_snapshot():
    now = timezone.now()
    cutoff = now - timedelta(seconds=95)
    heartbeat_rows = {row.queue: row for row in WorkerHeartbeat.objects.all()}
    depths = _queue_depths()
    queues = []
    for queue in settings.OPERATION_QUEUES:
        heartbeat = heartbeat_rows.get(queue)
        queues.append(
            {
                "name": queue,
                "fresh": bool(heartbeat and heartbeat.seen_at >= cutoff),
                "lag_seconds": heartbeat.lag_seconds if heartbeat else None,
                "depth": depths[queue],
            }
        )
    try:
        beat = cache.get("worker_heartbeat")
    except RedisError:
        beat = None
    beat_seen = parse_datetime(beat.get("seen_at", "")) if isinstance(beat, dict) else None
    protections = TradeProtection.objects.filter(coverage=TradeProtection.Coverage.MONITORED)
    ticks = [row.last_tick_at for row in protections.only("last_tick_at") if row.last_tick_at]
    feed_lag = max(int((now - value).total_seconds()) for value in ticks) if ticks else None
    pending = ExecutionOutbox.objects.exclude(state="done")
    oldest = pending.order_by("created_at").values_list("created_at", flat=True).first()
    errors = UserExchangeAccount.objects.filter(status=UserExchangeAccount.Status.ERROR).count()
    healthy = (
        all(item["fresh"] and item["depth"] is not None for item in queues)
        and bool(beat_seen and now - beat_seen < timedelta(seconds=95))
        and not pending.filter(dead_letter=True).exists()
        and errors == 0
    )
    return {
        "status": "healthy" if healthy else "degraded",
        "observed_at": now.isoformat(),
        "queues": queues,
        "scheduler": {
            "fresh": bool(beat_seen and now - beat_seen < timedelta(seconds=95)),
            "single_instance_lease": True,
        },
        "oldest_pending_seconds": int((now - oldest).total_seconds()) if oldest else 0,
        "feed_lag_seconds": feed_lag,
        "exchange_accounts_in_error": errors,
        "telegram_listener": "reserved_disabled_until_stage21",
        "real_order_writes": False,
    }
