"""Celery workers handle orders independently of browser sessions."""
from celery import shared_task

from .execution import dispatch_paper, expire_inflight
from .models import ExecutionOutbox


@shared_task(name="trading.process_paper", acks_late=True, reject_on_worker_lost=True)
def process_paper(outbox_id):
    return dispatch_paper(outbox_id)


@shared_task(name="trading.scan_outbox", acks_late=True)
def scan_outbox():
    expire_inflight()
    ids = list(ExecutionOutbox.objects.filter(state="pending")
               .order_by("created_at").values_list("pk", flat=True)[:20])
    for pk in ids:
        process_paper.apply_async(args=[pk], queue="orders")
    return {"queued": len(ids)}
