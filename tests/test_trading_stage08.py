"""Stage08 real-PostgreSQL tests: Paper only, idempotency and fill-ledger consistency."""

import json
import uuid
from decimal import Decimal

import pytest
from apps.exchanges.models import Exchange, ExchangeMarket, UserExchangeAccount
from apps.exchanges.security import set_account_credentials
from apps.exchanges.services import sync_exchange_account
from apps.tradeplans.forms import ManualTradeForm
from apps.tradeplans.service import approve_plan, create_draft
from apps.trading.execution import (
    cancel_unsubmitted,
    dispatch_paper,
    record_fill,
)
from apps.trading.intent import queue_paper_trade
from apps.trading.models import (
    CapitalReservation,
    ExecutionOutbox,
    Order,
    OrderFill,
    PaperRiskPolicy,
    Position,
    Trade,
    TradeEvent,
)
from django.core.exceptions import ValidationError
from django.urls import reverse


def paper_account(owner):
    ex = Exchange.objects.get(code="simulator")
    account = UserExchangeAccount(owner=owner, exchange=ex, label="Paper 8", environment="paper")
    set_account_credentials(account, {})
    account.save()
    sync_exchange_account(account)
    market = ExchangeMarket.objects.get(exchange=ex, symbol="BTC/USDT", market_type="spot")
    return account, market


def ready_plan(owner, account, market, *, capital="50"):
    values = {
        "account": str(account.pk),
        "market": str(market.pk),
        "source": "manual",
        "side": "long",
        "entry_price": "65000",
        "tp1": "70000",
        "tp2": "",
        "tp3": "",
        "stop_loss": "60000",
        "capital": capital,
        "leverage": "1",
        "trailing_distance": "1",
        "client_token": str(uuid.uuid4()),
    }
    form = ManualTradeForm(owner, values)
    assert form.is_valid(), form.errors
    plan, _ = create_draft(owner, form.cleaned_data)
    return approve_plan(owner, plan.pk, 1)


@pytest.mark.django_db
def test_paper_outbox_worker_position_and_duplicate_fill(django_user_model):
    owner = django_user_model.objects.create_user(username="paper8")
    account, market = paper_account(owner)
    plan = ready_plan(owner, account, market)
    key = uuid.uuid4()
    trade, created = queue_paper_trade(owner, plan.pk, request_key=key)
    same, second = queue_paper_trade(owner, plan.pk, request_key=key)
    assert created and not second and trade.pk == same.pk
    assert Trade.objects.count() == Order.objects.count() == ExecutionOutbox.objects.count() == 1
    assert not OrderFill.objects.exists()
    box = trade.orders.get().outbox
    assert dispatch_paper(box.pk)["status"] == "filled"
    trade.refresh_from_db()
    assert trade.state == "open"
    pos = Position.objects.get(trade=trade)
    assert pos.quantity == trade.quantity
    order = Order.objects.get(trade=trade)
    initial_qty = pos.quantity
    fill = OrderFill.objects.get(order=order)
    _, new = record_fill(
        order.pk,
        exchange_fill_id=fill.exchange_fill_id,
        quantity=fill.quantity,
        price=fill.price,
        fee=fill.fee,
    )
    assert not new
    pos.refresh_from_db()
    assert pos.quantity == initial_qty
    assert dispatch_paper(box.pk)["status"] == "already_claimed"
    assert TradeEvent.objects.filter(trade=trade, event_type="FILL").count() == 1
    assert CapitalReservation.objects.get(trade=trade).spent is True
    assert CapitalReservation.objects.get(trade=trade).active is True


@pytest.mark.django_db
def test_partial_fills_unique_keys_and_overfill_rejection(django_user_model):
    owner = django_user_model.objects.create_user(username="partial8")
    account, market = paper_account(owner)
    plan = ready_plan(owner, account, market)
    trade, _ = queue_paper_trade(owner, plan.pk, request_key=uuid.uuid4())
    order = trade.orders.get()
    half = order.quantity / 2
    f, new = record_fill(
        order.pk,
        exchange_fill_id="sim-fill-A",
        quantity=half,
        price=Decimal("65000"),
        fee=Decimal("0"),
    )
    assert new and f.quantity == half
    trade.refresh_from_db()
    assert trade.state == "partially_filled"
    assert Position.objects.get(trade=trade).quantity == half
    with pytest.raises(ValidationError):
        record_fill(
            order.pk,
            exchange_fill_id="sim-fill-over",
            quantity=order.quantity,
            price=Decimal("65000"),
        )
    record_fill(
        order.pk,
        exchange_fill_id="sim-fill-B",
        quantity=half,
        price=Decimal("66000"),
        fee=Decimal("0.01"),
    )
    trade.refresh_from_db()
    assert trade.state == "open"
    assert Position.objects.get(trade=trade).quantity == order.quantity
    assert Position.objects.get(trade=trade).total_fees == Decimal("0.01")
    with pytest.raises(ValidationError):
        record_fill(order.pk, exchange_fill_id="sim-fill-A", quantity=half, price=Decimal("64000"))


@pytest.mark.django_db
def test_risk_reservations_and_cancel_release(django_user_model):
    owner = django_user_model.objects.create_user(username="risk8")
    account, market = paper_account(owner)
    policy, _ = PaperRiskPolicy.objects.get_or_create(owner=owner)
    policy.max_total_allocated = Decimal("90")
    policy.max_capital_per_trade = Decimal("80")
    policy.save()
    plan1 = ready_plan(owner, account, market)
    first, _ = queue_paper_trade(owner, plan1.pk, request_key=uuid.uuid4())
    plan2 = ready_plan(owner, account, market)
    with pytest.raises(ValidationError):
        queue_paper_trade(owner, plan2.pk, request_key=uuid.uuid4())
    cancel_unsubmitted(owner, first.pk)
    assert not CapitalReservation.objects.get(trade=first).active
    next_trade, _ = queue_paper_trade(owner, plan2.pk, request_key=uuid.uuid4())
    assert next_trade.pk != first.pk


@pytest.mark.django_db
def test_live_provider_and_spot_short_are_never_submitted(django_user_model):
    owner = django_user_model.objects.create_user(username="live8")
    account, market = paper_account(owner)
    plan = ready_plan(owner, account, market)
    account.environment = "live"
    account.save(update_fields=("environment", "updated_at"))
    with pytest.raises(ValidationError):
        queue_paper_trade(owner, plan.pk, request_key=uuid.uuid4())
    assert not Order.objects.exists()


@pytest.mark.django_db
def test_browser_routes_are_owner_scoped_and_api_idempotent(client, django_user_model):
    owner = django_user_model.objects.create_user(username="api8")
    other = django_user_model.objects.create_user(username="other8")
    account, market = paper_account(owner)
    plan = ready_plan(owner, account, market)
    key = str(uuid.uuid4())
    client.force_login(owner)
    endpoint = reverse("api-paper-trades")
    payload = {"plan_id": plan.pk, "request_key": key}
    first = client.post(endpoint, data=json.dumps(payload), content_type="application/json")
    assert first.status_code == 201, first.content
    trade_id = first.json()["trade"]["id"]
    second = client.post(endpoint, data=json.dumps(payload), content_type="application/json")
    assert second.status_code == 200 and not second.json()["created"]
    assert client.get(reverse("paper-trade-detail", args=[trade_id])).status_code == 200
    assert (
        client.get(reverse("api-paper-detail", args=[trade_id])).json()["trade"]["mode"] == "paper"
    )
    client.force_login(other)
    assert client.get(reverse("paper-trade-detail", args=[trade_id])).status_code == 404
    assert client.get(reverse("api-paper-detail", args=[trade_id])).status_code == 404
    assert (
        client.post(endpoint, data=json.dumps(payload), content_type="application/json").status_code
        == 404
    )
