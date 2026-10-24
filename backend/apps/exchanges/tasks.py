import logging

from celery import shared_task
from django.core.exceptions import ValidationError
from django.utils import timezone

from .adapters import AdapterError
from .live_orders import execute_live_spot_order, reconcile_live_spot_order
from .models import LiveSpotOrder, UserExchangeAccount
from .services import sync_exchange_account as run_sync

logger = logging.getLogger(__name__)


@shared_task(name="exchanges.sync_account", acks_late=True, reject_on_worker_lost=True)
def sync_exchange_account(account_id):
    account = UserExchangeAccount.objects.select_related("exchange").get(pk=account_id)
    result = run_sync(account)
    external = None
    account.refresh_from_db()
    if (
        account.environment == "live"
        and account.status in {"connected", "restricted"}
        and account.permissions.get("can_read") is True
    ):
        try:
            from apps.operations.external import observe_account

            external = observe_account(account)
        except (AdapterError, ValidationError) as error:
            account.last_error_code = "external_refresh_failed"
            account.last_error_message = str(error)[:240]
            account.last_error_at = timezone.now()
            account.save(
                update_fields=(
                    "last_error_code",
                    "last_error_message",
                    "last_error_at",
                    "updated_at",
                )
            )
            external = {
                "status": "provider_read_failed",
                "error": type(error).__name__,
            }
    result["external"] = external
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



@shared_task(name="exchanges.reconcile_live_orders", acks_late=True, time_limit=45)
def reconcile_live_orders():
    from datetime import timedelta

    from django.utils import timezone

    cutoff = timezone.now() - timedelta(seconds=60)
    LiveSpotOrder.objects.filter(
        state=LiveSpotOrder.State.SUBMITTING,
        updated_at__lt=cutoff,
    ).update(
        state=LiveSpotOrder.State.UNCERTAIN,
        error_code="submission_worker_interrupted",
    )
    ids = list(
        LiveSpotOrder.objects.filter(
            state__in=(LiveSpotOrder.State.OPEN, LiveSpotOrder.State.PARTIAL),
            account__status="connected",
            account__permissions__can_read=True,
        )
        .exclude(external_order_id="")
        .order_by("updated_at", "pk")
        .values_list("pk", flat=True)[:100]
    )
    results = []
    for order_id in ids:
        try:
            results.append(
                {
                    "order_id": order_id,
                    "result": reconcile_live_spot_order(order_id),
                }
            )
        except Exception as error:
            logger.warning(
                "Live order reconciliation failed",
                extra={
                    "order_id": order_id,
                    "error": type(error).__name__,
                },
            )
    return {"processed": len(results), "results": results}
