import logging

from celery import shared_task

from .models import UserExchangeAccount
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
