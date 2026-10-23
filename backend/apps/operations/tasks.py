"""Maintenance stays independent of price, protective-exit and report queues."""

import logging
import os

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.exchanges.models import UserExchangeAccount
from apps.trading.execution import expire_inflight
from apps.trading.models import ExecutionOutbox

from .leases import lease
from .models import WorkerHeartbeat
from .monitoring import service_snapshot
from .recovery import raise_issue, reconcile_account, recover_outbox


@shared_task(bind=True, name="operations.heartbeat", ignore_result=True)
def heartbeat(self, queue):
    if queue not in settings.OPERATION_QUEUES:
        return
    now = timezone.now()
    sent = self.request.headers.get("sent_at") if self.request.headers else None
    seen = parse_datetime(sent) if sent else None
    lag = max(0, int((now - seen).total_seconds())) if seen else 0
    WorkerHeartbeat.objects.update_or_create(
        queue=queue,
        defaults={
            "seen_at": now,
            "worker": str(self.request.hostname or os.getpid())[:100],
            "lag_seconds": lag,
        },
    )
    cache.set("operations:heartbeat:" + queue, now.isoformat(), timeout=95)


@shared_task(name="operations.recover", acks_late=True, time_limit=120)
def recover():
    with lease("recovery", seconds=125) as acquired:
        if not acquired:
            return {"status": "busy"}
        expire_inflight(seconds=60)
        outcomes = []
        ids = (
            ExecutionOutbox.objects.filter(state__in=["uncertain", "error"])
            .order_by("updated_at")
            .values_list("pk", flat=True)[:50]
        )
        for pk in ids:
            try:
                outcomes.append(recover_outbox(pk))
            except Exception:
                box = ExecutionOutbox.objects.select_related("order").get(pk=pk)
                raise_issue(box.order.account_id, f"outbox:{pk}", "recovery_failed")
        for pk in (
            UserExchangeAccount.objects.filter(
                environment="paper", exchange__adapter_code="simulator"
            )
            .order_by("last_sync_at")
            .values_list("pk", flat=True)[:50]
        ):
            reconcile_account(pk)
        return {"processed": len(outcomes)}


@shared_task(name="operations.reconcile_one", acks_late=True, time_limit=120)
def reconcile_one(account_id):
    return reconcile_account(account_id)


logger = logging.getLogger(__name__)


@shared_task(name="operations.monitor", ignore_result=True)
def monitor_services():
    with lease("operations-monitor", seconds=55) as acquired:
        if not acquired:
            return {"status": "busy"}
        snapshot = service_snapshot()
        cache.set("operations:service-snapshot", snapshot, timeout=125)
        if snapshot["status"] != "healthy":
            logger.warning("Operational service snapshot is degraded")
        return snapshot


@shared_task(name="operations.monitor_external_trades", acks_late=True, time_limit=45)
def monitor_external_trades():
    from apps.portfolio.external_management import monitor_active_external_trades

    return monitor_active_external_trades()
