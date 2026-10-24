"""Stage24 signal archive lifecycle."""

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import Signal, SignalOutcome


def archive_expired_signals(*, owner=None):
    qs = Signal.objects.filter(
        archived_at__isnull=True,
        trashed_at__isnull=True,
        outcome__status=SignalOutcome.Status.EXPIRED,
    )
    if owner is not None:
        qs = qs.filter(owner=owner)
    now = timezone.now()
    return qs.update(archived_at=now)


@shared_task(name="signals.archive_expired", acks_late=True, time_limit=30)
def archive_expired_signals_task():
    with transaction.atomic():
        count = archive_expired_signals()
    return {"archived": count}
