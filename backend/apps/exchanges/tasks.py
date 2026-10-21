import logging

from celery import shared_task

from .live_orders import execute_live_spot_order
from .models import ExchangeConnectionLog, UserExchangeAccount
from .services import sync_exchange_account as run_sync

logger = logging.getLogger(__name__)


@shared_task(name="exchanges.sync_account", acks_late=True, reject_on_worker_lost=True)
def sync_exchange_account(account_id):
    account = UserExchangeAccount.objects.select_related("exchange").get(pk=account_id)
    ExchangeConnectionLog.objects.create(
        account=account,
        stage="worker",
        status=ExchangeConnectionLog.Status.RUNNING,
        message="Worker بررسی اتصال را آغاز کرد.",
    )
    try:
        result = run_sync(account)
    except Exception as error:
        ExchangeConnectionLog.objects.create(
            account=account,
            stage=getattr(error, "sync_stage", "sync"),
            status=ExchangeConnectionLog.Status.FAILED,
            code=getattr(error, "code", error.__class__.__name__)[:80],
            message="بررسی این مرحله ناموفق بود؛ کلید محرمانه در لاگ ذخیره نشده است.",
        )
        raise
    for stage, message in (
        ("credentials", "هویت API و سطح دسترسی خوانده شد."),
        ("markets", f"{result['market_count']} بازار فعال همگام شد."),
        ("balances", f"{result['balance_count']} موجودی دریافت شد."),
        ("complete", "اتصال با موفقیت بررسی و همگام شد."),
    ):
        ExchangeConnectionLog.objects.create(
            account=account,
            stage=stage,
            status=ExchangeConnectionLog.Status.SUCCESS,
            message=message,
        )
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
