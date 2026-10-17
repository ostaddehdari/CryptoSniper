"""Celery workers handle orders independently of browser sessions."""

from celery import shared_task
from django.utils import timezone

from .execution import dispatch_paper, expire_inflight
from .exits_tasks import (
    monitor_paper_exits as monitor_paper_exits,
)
from .exits_tasks import (
    paper_feed_staleness as paper_feed_staleness,
)
from .models import ExecutionOutbox


@shared_task(name="trading.process_paper", acks_late=True, reject_on_worker_lost=True)
def process_paper(outbox_id):
    return dispatch_paper(outbox_id)


@shared_task(name="trading.scan_outbox", acks_late=True)
def scan_outbox():
    expire_inflight()
    ids = list(
        ExecutionOutbox.objects.filter(
            state="pending",
            dead_letter=False,
            next_attempt_at__lte=timezone.now(),
            order__account__accountcontrol__paused=False,
        )
        .order_by("created_at")
        .values_list("pk", flat=True)[:20]
    )
    for pk in ids:
        process_paper.apply_async(args=[pk], queue="orders")
    return {"queued": len(ids)}
