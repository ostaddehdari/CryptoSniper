import logging

from celery import shared_task

from .live_orders import execute_live_spot_order
from .models import LiveSpotOrder, UserExchangeAccount
from .services import sync_exchange_account as run_sync

logger = logging.getLogger(__name__)


@shared_task(name="exchanges.sync_account", acks_late=True, reject_on_worker_lost=True)
def sync_exchange_account(account_id):
    account = UserExchangeAccount.objects.select_related("exchange").get(pk=account_id)
    result = run_sync(account)
    logger.info(
        "Exchange account synchronized",
        extra={
            "account_id": account_id,
            "exchange": account.exchange.code,
            "market_count": result["market_count"],
            "balance_count": result["balance_count"],
        },
    )
    return result


@shared_task(name="exchanges.live_spot_order", acks_late=True, reject_on_worker_lost=True)
def live_spot_order(order_id):
    return execute_live_spot_order(order_id)


@shared_task(name="exchanges.dispatch_pending_live_spot_orders", acks_late=True, time_limit=45)
def dispatch_pending_live_spot_orders():
    processed = 0
    for order_id in (
        LiveSpotOrder.objects.filter(state=LiveSpotOrder.State.PENDING)
        .order_by("created_at")
        .values_list("pk", flat=True)[:25]
    ):
        execute_live_spot_order(order_id)
        processed += 1
    return {"processed": processed}


@shared_task(name="exchanges.reconcile_live_spot_orders", acks_late=True, time_limit=90)
def reconcile_live_spot_orders():
    from apps.operations.leases import lease

    from .reconciliation import reconcile_order

    with lease("live-receipts", seconds=95) as acquired:
        if not acquired:
            return {"status": "busy"}
        ids = list(
            LiveSpotOrder.objects.exclude(state__in=("filled", "cancelled", "failed"))
            .order_by("updated_at")
            .values_list("pk", flat=True)[:20]
        )
        results = {}
        for pk in ids:
            try:
                results[str(pk)] = reconcile_order(pk)
            except Exception:
                # Provider errors never include raw credential-bearing exception text.
                results[str(pk)] = "unresolved"
        return results
