"""Recovery and Stage27 owner-scoped UI/API acceptance on PostgreSQL and Redis."""

import json
import uuid
from decimal import Decimal

import pytest
from apps.exchanges.adapters import Order as ProviderOrder
from apps.exchanges.adapters import OrderStatus
from apps.exchanges.live_orders import reconcile_live_spot_order
from apps.exchanges.models import LiveSpotOrder
from apps.operations.models import AccountControl, PaperProviderOrder, RecoveryIssue
from apps.operations.recovery import recover_outbox
from apps.signals.models import Signal
from apps.trading.execution import claim_outbox, dispatch_paper, mark_uncertain, record_fill
from apps.trading.exits_engine import process_paper_price
from apps.trading.intent import queue_paper_trade
from apps.trading.models import OrderFill, PaperExitFill, Position, TradeEvent
from django.urls import reverse
from django.utils import timezone
from test_trading_stage08 import paper_account, ready_plan


@pytest.mark.django_db
def test_worker_restart_looks_up_receipt_before_retry_and_repeats_no_fill(django_user_model):
    owner = django_user_model.objects.create_user(username="s26-restart")
    account, market = paper_account(owner)
    trade, _ = queue_paper_trade(owner, ready_plan(owner, account, market).pk, request_key=uuid.uuid4())
    box = trade.orders.get().outbox
    claim_outbox(box.pk)
    from apps.operations.provider import submit

    receipt = submit(trade.orders.select_related("account__exchange", "trade__market").get())
    assert recover_outbox(box.pk) == "recovered"
    assert recover_outbox(box.pk) == "unchanged"
    assert OrderFill.objects.filter(order__trade=trade).count() == 1
    assert PaperProviderOrder.objects.get(account=account) == receipt
    assert TradeEvent.objects.filter(trade=trade, event_type="RECOVERED_PROVIDER_RECEIPT").count() == 1


@pytest.mark.django_db
def test_missing_partial_receipt_pauses_account_and_cannot_requeue(django_user_model):
    owner = django_user_model.objects.create_user(username="s26-partial")
    account, market = paper_account(owner)
    trade, _ = queue_paper_trade(owner, ready_plan(owner, account, market).pk, request_key=uuid.uuid4())
    box = trade.orders.get().outbox
    claim_outbox(box.pk)
    order = trade.orders.get()
    record_fill(order.pk, exchange_fill_id="partial-before-crash", quantity=order.quantity / 2, price=order.price)
    mark_uncertain(box.pk)
    assert recover_outbox(box.pk) == "partial_requires_reconciliation"
    assert AccountControl.objects.get(account=account).paused
    assert RecoveryIssue.objects.get(account=account, key=f"outbox:{box.pk}").code == "partial_receipt_missing"
    assert dispatch_paper(box.pk)["status"] == "already_claimed"
    assert Position.objects.get(trade=trade).quantity == order.quantity / 2


@pytest.mark.django_db
def test_mismatched_provider_receipt_is_disclosed_and_not_consumed(django_user_model):
    owner = django_user_model.objects.create_user(username="s26-mismatch")
    account, market = paper_account(owner)
    trade, _ = queue_paper_trade(owner, ready_plan(owner, account, market).pk, request_key=uuid.uuid4())
    box = trade.orders.get().outbox
    claim_outbox(box.pk)
    from apps.operations.provider import submit

    receipt = submit(trade.orders.select_related("account__exchange", "trade__market").get())
    PaperProviderOrder.objects.filter(pk=receipt.pk).update(quantity=receipt.quantity + 1)
    assert recover_outbox(box.pk) == "discrepancy"
    assert RecoveryIssue.objects.get(account=account, key=f"outbox:{box.pk}").code == "receipt_mismatch"
    assert AccountControl.objects.get(account=account).paused
    assert not OrderFill.objects.filter(order__trade=trade).exists()


@pytest.mark.django_db
def test_live_uncertain_recovery_is_read_only_and_absence_stays_unknown(monkeypatch, django_user_model):
    owner = django_user_model.objects.create_user(username="s26-live-observe")
    account, market = paper_account(owner)
    order = LiveSpotOrder.objects.create(
        owner=owner, account=account, market=market, request_key=uuid.uuid4(),
        client_order_id="recovery-read-only", side="buy", order_type="limit",
        amount=Decimal("0.001"), price=Decimal("65000"), state="uncertain",
    )

    class FakeAdapter:
        def __init__(self):
            self.placed = 0

        def fetch_open_orders(self):
            return []

        def place_order(self, **_):
            self.placed += 1
            raise AssertionError("Recovery must not submit")

    adapter = FakeAdapter()
    monkeypatch.setattr("apps.exchanges.live_orders.get_adapter", lambda *a, **kw: adapter)
    monkeypatch.setattr("apps.exchanges.live_orders.get_account_credentials", lambda a: {})
    assert reconcile_live_spot_order(order.pk) == "unknown"
    assert AccountControl.objects.get(account=account).paused
    assert adapter.placed == 0
    adapter.fetch_open_orders = lambda: [ProviderOrder(
        order_id="provider-1", client_order_id=order.client_order_id, symbol=market.symbol,
        side="buy", order_type="limit", amount=order.amount, price=order.price,
        filled_amount=Decimal("0.0005"), average_price=order.price,
        status=OrderStatus.PARTIAL, created_at=timezone.now(),
    )]
    assert reconcile_live_spot_order(order.pk) == "recovered"
    order.refresh_from_db()
    assert order.state == "partial" and order.filled_amount == Decimal("0.0005")
    assert adapter.placed == 0
    assert RecoveryIssue.objects.get(account=account, key=f"live-order:{order.pk}").resolved


@pytest.mark.django_db
def test_paper_manual_and_smart_paste_owner_audit_retry_to_exit(client, django_user_model):
    owner = django_user_model.objects.create_user(username="s26-e2e")
    other = django_user_model.objects.create_user(username="s26-e2e-other")
    account, market = paper_account(owner)
    client.force_login(owner)
    paste = client.post(
        reverse("api-smart-paste"),
        data=json.dumps({"text": "BTC/USDT LONG Entry 65000 TP1 70000 SL 60000"}),
        content_type="application/json",
    )
    assert paste.status_code in {200, 201}
    signal_id = paste.json()["signal"]["id"]
    assert Signal.objects.get(pk=signal_id).owner_id == owner.pk
    plan = ready_plan(owner, account, market)
    key = uuid.uuid4()
    trade, created = queue_paper_trade(owner, plan.pk, request_key=key)
    same, replayed = queue_paper_trade(owner, plan.pk, request_key=key)
    assert created and not replayed and same.pk == trade.pk
    assert dispatch_paper(trade.orders.get().outbox.pk)["status"] == "filled"
    assert process_paper_price(trade.pk, price="70000", event_key="s26-final-exit")["status"] == "closed"
    assert PaperExitFill.objects.filter(trade=trade).count() == 1
    assert TradeEvent.objects.filter(trade=trade, event_type="PAPER_CLOSED").count() == 1
    client.force_login(other)
    assert client.get(reverse("api-inbox-detail", args=[signal_id])).status_code == 404
    assert client.get(f"/paper/{trade.pk}/").status_code == 404
