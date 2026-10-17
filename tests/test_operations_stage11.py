"""Real PostgreSQL + Redis tests; failure injection is labelled, never provider evidence."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from apps.operations import provider
from apps.operations.leases import client as redis_client
from apps.operations.leases import lease
from apps.operations.models import AccountControl, PaperProviderOrder, RecoveryIssue
from apps.operations.recovery import (
    classify_failure,
    reconcile_account,
    reconcile_trade,
    recover_outbox,
)
from apps.operations.views import set_paused
from apps.trading.execution import claim_outbox, consume_receipt, dispatch_paper, expire_inflight
from apps.trading.intent import queue_paper_trade
from apps.trading.models import ExecutionOutbox, OrderFill, Position, Trade
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.urls import reverse
from django.utils import timezone
from test_trading_stage08 import paper_account, ready_plan


def setup_trade(user):
    account, market = paper_account(user)
    plan = ready_plan(user, account, market)
    trade, _ = queue_paper_trade(user, plan.pk, request_key=uuid.uuid4())
    return trade, trade.orders.get().outbox


@pytest.mark.django_db(transaction=True)
def test_parallel_workers_one_durable_order_and_fill(django_user_model):
    user = django_user_model.objects.create_user(username="concurrent11")
    trade, box = setup_trade(user)

    def worker():
        close_old_connections()
        try:
            return dispatch_paper(box.pk)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: worker(), range(2)))
    assert PaperProviderOrder.objects.count() == OrderFill.objects.count() == 1
    assert Position.objects.get(trade=trade).quantity == trade.quantity


@pytest.mark.django_db
def test_receipt_survives_executor_crash_and_recovery_is_idempotent(django_user_model):
    user = django_user_model.objects.create_user(username="crash11")
    trade, box = setup_trade(user)
    claim_outbox(box.pk)
    receipt = provider.submit(
        trade.orders.select_related("account__exchange", "trade__market").get()
    )
    # Inject a crash after provider commit, before consuming its response.
    ExecutionOutbox.objects.filter(pk=box.pk).update(
        updated_at=timezone.now() - timedelta(minutes=2)
    )
    assert expire_inflight(60) == 1
    assert recover_outbox(box.pk) == "recovered"
    assert consume_receipt(box.pk, receipt)["status"] == "already_claimed"
    assert PaperProviderOrder.objects.count() == OrderFill.objects.count() == 1
    assert reconcile_account(trade.account_id) == "ok"


@pytest.mark.django_db
def test_timeout_after_provider_created_order_is_looked_up(monkeypatch, django_user_model):
    user = django_user_model.objects.create_user(username="timeout11")
    trade, box = setup_trade(user)
    original = provider.submit

    def timeout_after_commit(order):
        original(order)
        raise TimeoutError("injected test timeout")

    monkeypatch.setattr(provider, "submit", timeout_after_commit)
    assert dispatch_paper(box.pk)["status"] == "uncertain"
    assert recover_outbox(box.pk) == "recovered"
    assert PaperProviderOrder.objects.count() == OrderFill.objects.count() == 1
    assert Trade.objects.get(pk=trade.pk).state == "open"


@pytest.mark.django_db
def test_expired_lease_release_cannot_release_successor():
    with lease("test-lease11") as first:
        assert first
        redis_client().delete("cs:lease:test-lease11")  # Failure injection: expiry.
        with lease("test-lease11") as second:
            assert second
        assert redis_client().get("cs:lease:test-lease11") is None


@pytest.mark.django_db
def test_old_fence_cannot_consume_receipt(django_user_model):
    user = django_user_model.objects.create_user(username="fence11")
    trade, box = setup_trade(user)
    claim_outbox(box.pk)
    box.refresh_from_db()
    receipt = provider.submit(
        trade.orders.select_related("account__exchange", "trade__market").get()
    )
    assert consume_receipt(box.pk, receipt, fence=box.fence - 1)["status"] == "fenced"
    assert not OrderFill.objects.exists()
    assert consume_receipt(box.pk, receipt, fence=box.fence)["status"] == "filled"


@pytest.mark.django_db
def test_pause_resume_and_sensitive_discrepancy(django_user_model):
    user = django_user_model.objects.create_user(username="pause11")
    trade, box = setup_trade(user)
    control = set_paused(user, trade.account_id, paused=True, version=1)
    assert claim_outbox(box.pk) is None
    with pytest.raises(ValidationError):
        set_paused(user, trade.account_id, paused=False, version=control.version)
    reconcile_account(trade.account_id)
    set_paused(user, trade.account_id, paused=False, version=control.version)
    assert dispatch_paper(box.pk)["status"] == "filled"
    Position.objects.filter(trade=trade).update(quantity=Decimal("0.7"))
    assert reconcile_trade(trade.pk) == "repaired"
    assert Position.objects.get(trade=trade).quantity == trade.quantity
    trade.account.balance_snapshots.update(free_balance=0)
    assert reconcile_account(trade.account_id) == "issues"
    assert RecoveryIssue.objects.filter(resolved=False, code="balance_discrepancy").exists()
    assert AccountControl.objects.get(account=trade.account).paused


@pytest.mark.django_db
def test_retry_is_bounded_and_dead_letter_pauses(django_user_model):
    user = django_user_model.objects.create_user(username="retry11")
    trade, box = setup_trade(user)
    ExecutionOutbox.objects.filter(pk=box.pk).update(state="uncertain", attempts=5)
    classify_failure(box.pk, TimeoutError())
    box.refresh_from_db()
    assert box.dead_letter and box.next_attempt_at > timezone.now()
    assert recover_outbox(box.pk) == "dead_letter"
    assert AccountControl.objects.get(account=trade.account).paused


@pytest.mark.django_db
def test_operations_owner_scope_and_version(client, django_user_model):
    user = django_user_model.objects.create_user(username="ownerops11")
    other = django_user_model.objects.create_user(username="otherops11")
    trade, _ = setup_trade(user)
    client.force_login(other)
    assert (
        client.post(
            reverse("operations-control", args=[trade.account_id]),
            {"action": "pause", "version": 1},
        ).status_code
        == 404
    )
    assert client.get(reverse("operations")).status_code == 200
    assert str(trade.account.label).encode() not in client.get(reverse("operations")).content
    with pytest.raises(ValidationError):
        set_paused(user, trade.account_id, paused=True, version=12)


@pytest.mark.django_db
def test_redis_outage_fails_before_claim(settings, django_user_model):
    from redis.exceptions import ConnectionError

    user = django_user_model.objects.create_user(username="outage11")
    _, box = setup_trade(user)
    settings.CELERY_BROKER_URL = "redis://127.0.0.1:1/0"
    with pytest.raises(ConnectionError):
        dispatch_paper(box.pk)
    box.refresh_from_db()
    assert box.state == "pending" and box.attempts == 0
    assert not PaperProviderOrder.objects.exists()


@pytest.mark.django_db
def test_external_observations_are_readonly(monkeypatch, django_user_model):
    """Fake Binance transport validates read contracts only, not a real account."""
    from apps.exchanges.models import Exchange, UserExchangeAccount
    from apps.exchanges.security import set_account_credentials
    from apps.operations.external import observe_binance
    from apps.operations.models import ExternalObservation
    from test_binance_adapter import adapter_with

    user = django_user_model.objects.create_user(username="external11")
    account = UserExchangeAccount(
        owner=user,
        exchange=Exchange.objects.get(code="binance"),
        label="External",
        environment="live",
        status="restricted",
        permissions={"can_read": True},
    )
    set_account_credentials(account, {"api_key": "fake", "api_secret": "fake"})
    account.save()
    adapter = adapter_with(
        {
            "/sapi/v1/account/apiRestrictions": {
                "enableReading": True,
                "enableWithdrawals": False,
                "enableSpotAndMarginTrading": False,
            },
            "/api/v3/account": {"balances": [{"asset": "USDT", "free": "100", "locked": "0"}]},
            "/api/v3/openOrders": [
                {
                    "symbol": "BTCUSDT",
                    "orderId": 1,
                    "clientOrderId": "outside-cs",
                    "origQty": ".001",
                    "executedQty": "0",
                    "status": "NEW",
                }
            ],
        }
    )
    monkeypatch.setattr("apps.operations.external.get_adapter", lambda *args, **kwargs: adapter)
    assert observe_binance(account) == "read_only_snapshot"
    assert ExternalObservation.objects.filter(account=account).count() == 2
    assert not Trade.objects.filter(account=account).exists()
    assert all(call[0] == "GET" for call in adapter.transport.calls)


@pytest.mark.django_db
def test_dead_letter_discard_is_safe_and_owner_scoped(client, django_user_model):
    user = django_user_model.objects.create_user(username="discard11")
    trade, box = setup_trade(user)
    claim_outbox(box.pk)
    ExecutionOutbox.objects.filter(pk=box.pk).update(
        state="uncertain", attempts=5, dead_letter=True
    )
    box.refresh_from_db()
    client.force_login(user)
    endpoint = reverse("operations-resolve-dead-letter", args=[box.pk])
    assert client.post(endpoint, {"fence": 999}).status_code == 409
    assert client.post(endpoint, {"fence": box.fence}).status_code == 302
    trade.refresh_from_db()
    assert trade.state == "failed" and not trade.reservation.active
    # A delayed provider submit after discard cannot create a new receipt.
    with pytest.raises(ValidationError):
        provider.submit(trade.orders.get())
    assert not PaperProviderOrder.objects.exists()
