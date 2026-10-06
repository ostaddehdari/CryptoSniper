import logging
import os

from celery import shared_task
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .models import ServiceProbe
from .observability import correlation_id

logger = logging.getLogger(__name__)


@shared_task(name="core.infrastructure_probe", acks_late=True)
def infrastructure_probe(probe_id):
    with transaction.atomic():
        probe = ServiceProbe.objects.select_for_update().get(pk=probe_id)
        token = correlation_id.set(str(probe.correlation_id))
        try:
            if probe.status != "succeeded":
                probe.status = "succeeded"
                probe.worker_pid = os.getpid()
                probe.completed_at = timezone.now()
                probe.save(update_fields=["status", "worker_pid", "completed_at"])
                logger.info("Infrastructure probe completed on queue %s", probe.queue)
            return {
                "probe_id": str(probe.id),
                "worker_pid": probe.worker_pid,
                "queue": probe.queue,
                "correlation_id": str(probe.correlation_id),
            }
        finally:
            correlation_id.reset(token)


@shared_task(name="core.worker_heartbeat", ignore_result=True)
def worker_heartbeat():
    cache.set(
        "worker_heartbeat", {"seen_at": timezone.now().isoformat(), "pid": os.getpid()}, timeout=90
    )
