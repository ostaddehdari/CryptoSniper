import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.exchanges.adapters import Order, OrderStatus
from apps.exchanges.live_orders import execute_live_spot_order, reconcile_live_spot_order
from apps.exchanges.models import (
    Asset,
    BalanceSnapshot,
    Exchange,
    ExchangeMarket,
    LiveSpotOrder,
    UserExchangeAccount,
)
from apps.operations.external_management import adopt_or_update, monitor_one
from apps.operations.managed_live import (
    create_management as create_managed_live,
    monitor_one as monitor_managed_live,
)
from apps.operations.models import (
    ExternalObservation,
    AccountControl,
    ExternalTradeManagement,
    ManagedLiveExit,
    ManagedLiveTrade,
)
from apps.tradeplans.models import TradePlan
from apps.signals.models import RawSignal, Signal, SignalSource, SignalTarget


def live_account(owner, code="bitunix", label="main"):
    exchange = Exchange.objects.get(code=code)
    return UserExchangeAccount.objects.create(
        owner=owner,
        exchange=exchange,
        label=label,
        environment="live",
        status="connected",
        trading_enabled=True,
        permissions={
            "can_read": True,
            "can_trade_spot": True,
            "can_trade_margin": False,
            "can_withdraw": False,
        },
    )


def spot_market(account, symbol="BTC/USDT", *, fee=Decimal("0.001")):
    base_name, quote_name = symbol.split("/")
    base, _ = Asset.objects.get_or_create(symbol=base_name)
    quote, _ = Asset.objects.get_or_create(symbol=quote_name)
    return ExchangeMarket.objects.create(
        exchange=account.exchange,
        symbol=symbol,
        base_asset=base,
        quote_asset=quote,
        market_type="spot",
        min_amount=Decimal("0.001"),
        amount_step=Decimal("0.001"),
        price_step=Decimal("1"),
        min_notional=None,
        max_leverage=Decimal("1"),
        taker_fee=fee,
        active=True,
        synced_at=timezone.now(),
    )


def ready_live_plan(owner, account, market, *, trailing=True, trailing_sl=True, trigger="tp2"):
    preview = {
        "quantity": "1.000",
        "targets": [
            {"price": "110", "share_percent": "10"},
            {"price": "120", "share_percent": "10"},
            {"price": "130", "share_percent": "80"},
        ]
    }
    return TradePlan.objects.create(
        owner=owner,
        exchange_account=account,
        market=market,
        source="manual",
        status=TradePlan.Status.READY,
        side=TradePlan.Side.LONG,
        entry_price=Decimal("100"),
        stop_loss=Decimal("90"),
        tp1=Decimal("110"),
        tp2=Decimal("120"),
        tp3=Decimal("130"),
        capital=Decimal("100"),
        leverage=Decimal("1"),
        trailing_sl=trailing_sl,
        percentage_trailing=trailing,
        percentage_trigger=trigger,
        trailing_distance=Decimal("1"),
        preview=preview,
        approved_snapshot=preview,
        approved_at=timezone.now(),
    )


@pytest.mark.django_db
def test_stage27_trade_plan_allows_missing_fee_and_min_notional(client, django_user_model):
    owner = django_user_model.objects.create_user(username="stage27-plan")
    account = live_account(owner)
    market = spot_market(account, fee=None)
    BalanceSnapshot.objects.create(
        exchange_account=account,
        asset=market.quote_asset,
        free_balance=Decimal("1000"),
        locked_balance=Decimal("0"),
        total_balance=Decimal("1000"),
        captured_at=timezone.now(),
    )
    client.force_login(owner)
    response = client.post(
        reverse("api-manual-create"),
        data=json.dumps(
            {
                "account": account.pk,
                "market": market.pk,
                "source": "manual",
                "side": "long",
                "entry_price": "100",
                "tp1": "110",
                "tp2": "120",
                "tp3": "130",
                "stop_loss": "90",
                "capital": "100",
                "leverage": "1",
                "trailing_sl": True,
                "percentage_trailing": True,
                "percentage_trigger": "tp2",
                "trailing_distance": "1",
                "client_token": str(uuid.uuid4()),
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    snapshot = response.json()["plan"]["snapshot"]
    assert snapshot["percentage_trigger"] == "tp2"
    assert snapshot["fee_rate_known"] is False
    assert snapshot["min_notional_known"] is False


@pytest.mark.django_db
def test_stage27_preferences_accept_tp3_trigger_and_return_integers(client, django_user_model):
    owner = django_user_model.objects.create_user(username="stage27-pref")
    client.force_login(owner)
    response = client.patch(
        reverse("api-trading-preferences"),
        data=json.dumps(
            {
                "default_order_amount": "75",
                "default_market": "spot",
                "tp1_percent": "10",
                "tp2_percent": "20",
                "tp3_percent": "70",
                "trailing_sl_enabled": True,
                "trailing_tp_enabled": True,
                "trailing_trigger": "tp3",
                "trailing_distance_percent": "2",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    data = response.json()["trading_preferences"]
    assert data["default_order_amount"] == "75"
    assert data["tp_distribution"] == ["10", "20", "70"]
    assert data["trailing_trigger"] == "tp3"
    assert data["trailing_distance_percent"] == "2"


@pytest.mark.django_db
def test_stage27_bulk_signal_delete_is_owner_scoped(client, django_user_model):
    owner = django_user_model.objects.create_user(username="stage27-signals")
    other = django_user_model.objects.create_user(username="stage27-other")
    source = SignalSource.objects.create(owner=owner, name="manual", method="manual")
    other_source = SignalSource.objects.create(owner=other, name="manual", method="manual")
    ids = []
    for index in range(2):
        raw = RawSignal.objects.create(
            owner=owner,
            source=source,
            original_text=f"signal {index}",
            original_payload={},
            checksum=f"stage27-{index}",
        )
        ids.append(Signal.objects.create(owner=owner, source=source, raw_signal=raw).pk)
    other_raw = RawSignal.objects.create(
        owner=other,
        source=other_source,
        original_text="other",
        original_payload={},
        checksum="stage27-other",
    )
    other_signal = Signal.objects.create(owner=other, source=other_source, raw_signal=other_raw)
    client.force_login(owner)
    response = client.post(
        reverse("api-inbox-bulk-action"),
        data=json.dumps({"action": "delete", "ids": ids}),
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["count"] == 2
    assert not Signal.objects.filter(pk__in=ids).exists()
    assert Signal.objects.filter(pk=other_signal.pk).exists()


@pytest.mark.django_db
def test_stage27_operations_hides_disabled_exchange_accounts(client, django_user_model):
    owner = django_user_model.objects.create_user(username="stage27-ops")
    active = live_account(owner, label="active")
    disabled = live_account(owner, label="deleted")
    disabled.status = "disabled"
    disabled.trading_enabled = False
    disabled.save(update_fields=("status", "trading_enabled", "updated_at"))
    client.force_login(owner)
    response = client.get(reverse("api-operations-health"))
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["accounts"]}
    assert active.pk in ids
    assert disabled.pk not in ids


@pytest.mark.django_db
def test_stage27_exchange_revoke_keeps_web_session_authenticated(client, django_user_model):
    password = "stage27-password-very-long"
    owner = django_user_model.objects.create_user(
        username="stage27-revoke",
        password=password,
    )
    account = live_account(owner)
    account.credentials_encrypted = "placeholder"
    account.credential_hint = "•••• test"
    account.save(update_fields=("credentials_encrypted", "credential_hint", "updated_at"))
    client.force_login(owner)
    step = client.post(
        reverse("api-step-up"),
        data=json.dumps({"password": password}),
        content_type="application/json",
    )
    assert step.status_code == 200, step.content
    response = client.post(
        reverse("api-exchange-revoke", args=[account.pk]),
        data=json.dumps({"confirmed": True}),
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    assert client.get(reverse("api-ui-bootstrap")).status_code == 200
    account.refresh_from_db()
    assert account.status == "disabled"


@pytest.mark.django_db
def test_stage27_smart_paste_materializes_compact_pair_on_unique_market(
    client, django_user_model
):
    owner = django_user_model.objects.create_user(username="stage27-parser")
    account = live_account(owner)
    spot_market(account)
    client.force_login(owner)
    response = client.post(
        reverse("api-smart-paste"),
        data=json.dumps(
            {
                "text": (
                    "BTCUSDT\nLONG\nENTRY 80000\n"
                    "TP1 82000\nTP2 84000\nTP3 86000\nSL 78000"
                )
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    signal = response.json()["signal"]
    assert signal["status"] == "parsed"
    structured = signal["structured"]
    assert structured["account_id"] == account.pk
    assert structured["market_id"] is not None
    assert structured["entry"] == "80000"
    assert structured["stop_loss"] == "78000"
    assert len(structured["targets"]) == 3


@pytest.mark.django_db
@override_settings(LIVE_TRADING_ENABLED=True)
def test_stage27_external_trailing_sl_moves_to_entry_once_and_queues_one_exit(
    monkeypatch, django_user_model
):
    owner = django_user_model.objects.create_user(username="stage27-external")
    account = live_account(owner)
    spot_market(account)
    observation = ExternalObservation.objects.create(
        account=account,
        kind="fill",
        external_id="BTCUSDT:123",
        payload={
            "symbol": "BTCUSDT",
            "side": "buy",
            "executedQty": "0.010",
            "averagePrice": "100",
            "status": "filled",
        },
    )
    item = adopt_or_update(
        owner,
        observation.pk,
        {
            "quantity": "0.010",
            "entry_price": "100",
            "stop_loss": "90",
            "tp1": "110",
            "tp2": "120",
            "tp3": "130",
            "trailing_enabled": False,
            "trailing_sl_enabled": True,
            "trailing_trigger": "tp1",
            "trailing_distance_percent": "1",
        },
    )
    price = {"value": Decimal("110")}
    monkeypatch.setattr(
        "apps.operations.external_management.refresh_live_quote",
        lambda market: {
            "status": "ok",
            "data": {"price": str(price["value"]), "stale": False},
        },
    )
    monkeypatch.setattr(
        "apps.operations.external_management._provider_free_base",
        lambda item: Decimal("1"),
    )
    queued = []
    monkeypatch.setattr(
        "apps.operations.external_management.live_spot_order.apply_async",
        lambda args, queue: queued.append((args, queue)),
    )
    monkeypatch.setattr(
        "apps.operations.external_management.transaction.on_commit",
        lambda callback: callback(),
    )

    assert monitor_one(item.pk) == "monitored"
    item.refresh_from_db()
    assert item.breakeven_moved is True
    assert item.effective_stop == Decimal("100")

    price["value"] = Decimal("120")
    assert monitor_one(item.pk) == "monitored"
    item.refresh_from_db()
    assert item.effective_stop == Decimal("100")

    price["value"] = Decimal("99")
    assert monitor_one(item.pk) == "exit_queued"
    item.refresh_from_db()
    assert item.state == ExternalTradeManagement.State.EXITING
    assert item.exit_order_id is not None
    order = LiveSpotOrder.objects.get(pk=item.exit_order_id)
    assert order.side == "sell"
    assert order.order_type == "market"
    assert order.amount == Decimal("0.010")
    assert len(queued) == 1



@pytest.mark.django_db
@override_settings(LIVE_TRADING_ENABLED=True)
def test_stage27_live_order_api_queues_without_provider_call(
    client, django_user_model, monkeypatch
):
    password = "stage27-live-order-password"
    owner = django_user_model.objects.create_user(
        username="stage27-live-order",
        password=password,
    )
    account = live_account(owner)
    market = spot_market(account)
    queued = []
    monkeypatch.setattr(
        "apps.core.react_views.live_spot_order.apply_async",
        lambda args, queue: queued.append((args, queue)),
    )
    monkeypatch.setattr(
        "apps.core.react_views.transaction.on_commit",
        lambda callback: callback(),
    )
    client.force_login(owner)
    step = client.post(
        reverse("api-step-up"),
        data=json.dumps({"password": password}),
        content_type="application/json",
    )
    assert step.status_code == 200
    response = client.post(
        reverse("api-live-orders"),
        data=json.dumps(
            {
                "account": account.pk,
                "market": market.pk,
                "side": "buy",
                "amount": "1.000",
                "price": "100",
                "confirmed": True,
                "request_key": str(uuid.uuid4()),
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    order = LiveSpotOrder.objects.get(pk=response.json()["order"]["id"])
    assert order.state == LiveSpotOrder.State.PENDING
    assert order.order_type == "limit"
    assert queued == [([order.pk], "orders")]



@pytest.mark.django_db
def test_stage27_live_order_reconcile_updates_existing_order_without_resubmit(
    monkeypatch, django_user_model
):
    owner = django_user_model.objects.create_user(username="stage27-reconcile")
    account = live_account(owner)
    market = spot_market(account)
    order = LiveSpotOrder.objects.create(
        owner=owner,
        account=account,
        market=market,
        request_key=uuid.uuid4(),
        client_order_id="stage27-reconcile-order",
        external_order_id="provider-123",
        side="buy",
        order_type="limit",
        amount=Decimal("1"),
        price=Decimal("100"),
        state=LiveSpotOrder.State.OPEN,
    )

    class FakeAdapter:
        def fetch_order(self, order_id):
            assert order_id == "provider-123"
            return Order(
                order_id=order_id,
                client_order_id="stage27-reconcile-order",
                symbol="BTC/USDT",
                side="buy",
                order_type="limit",
                amount=Decimal("1"),
                price=Decimal("100"),
                filled_amount=Decimal("1"),
                average_price=Decimal("99.5"),
                status=OrderStatus.FILLED,
                created_at=datetime.now(UTC),
            )

    monkeypatch.setattr(
        "apps.exchanges.live_orders.get_account_credentials",
        lambda account: {},
    )
    monkeypatch.setattr(
        "apps.exchanges.live_orders.get_adapter",
        lambda *args, **kwargs: FakeAdapter(),
    )
    outcome = reconcile_live_spot_order(order.pk)
    assert outcome["status"] == LiveSpotOrder.State.FILLED
    order.refresh_from_db()
    assert order.state == LiveSpotOrder.State.FILLED
    assert order.filled_amount == Decimal("1")
    assert order.average_price == Decimal("99.5")



@pytest.mark.django_db
@override_settings(LIVE_TRADING_ENABLED=True)
def test_stage27_managed_live_waits_for_full_entry_fill(
    monkeypatch, django_user_model
):
    owner = django_user_model.objects.create_user(username="stage27-managed-pending")
    account = live_account(owner)
    market = spot_market(account)
    plan = ready_live_plan(owner, account, market)
    entry = LiveSpotOrder.objects.create(
        owner=owner,
        account=account,
        market=market,
        request_key=uuid.uuid4(),
        client_order_id="stage27-managed-entry-partial",
        external_order_id="provider-entry-partial",
        side="buy",
        order_type="limit",
        amount=Decimal("1"),
        price=Decimal("100"),
        filled_amount=Decimal("0.5"),
        average_price=Decimal("100"),
        state=LiveSpotOrder.State.PARTIAL,
    )
    management = create_managed_live(owner, plan.pk, entry)
    monkeypatch.setattr(
        "apps.operations.managed_live.refresh_live_quote",
        lambda market: {
            "status": "ok",
            "data": {"price": "150", "stale": False},
        },
    )
    assert monitor_managed_live(management.pk) == ManagedLiveTrade.State.PENDING_ENTRY
    management.refresh_from_db()
    assert management.state == ManagedLiveTrade.State.PENDING_ENTRY
    assert management.initial_quantity == Decimal("0")
    assert not LiveSpotOrder.objects.filter(side="sell").exists()


@pytest.mark.django_db
@override_settings(LIVE_TRADING_ENABLED=True)
def test_stage27_managed_live_trailing_sl_and_full_exit_are_idempotent(
    monkeypatch, django_user_model
):
    owner = django_user_model.objects.create_user(username="stage27-managed-live")
    account = live_account(owner)
    market = spot_market(account)
    plan = ready_live_plan(
        owner,
        account,
        market,
        trailing=True,
        trailing_sl=True,
        trigger="tp2",
    )
    entry = LiveSpotOrder.objects.create(
        owner=owner,
        account=account,
        market=market,
        request_key=uuid.uuid4(),
        client_order_id="stage27-managed-entry",
        external_order_id="provider-entry-filled",
        side="buy",
        order_type="limit",
        amount=Decimal("1"),
        price=Decimal("100"),
        filled_amount=Decimal("1"),
        average_price=Decimal("100"),
        state=LiveSpotOrder.State.FILLED,
    )
    management = create_managed_live(owner, plan.pk, entry)
    price = {"value": Decimal("110")}
    monkeypatch.setattr(
        "apps.operations.managed_live.refresh_live_quote",
        lambda market: {
            "status": "ok",
            "data": {"price": str(price["value"]), "stale": False},
        },
    )
    monkeypatch.setattr(
        "apps.operations.managed_live._provider_free_base",
        lambda item: Decimal("10"),
    )
    queued = []
    monkeypatch.setattr(
        "apps.operations.managed_live.live_spot_order.apply_async",
        lambda args, queue: queued.append((args, queue)),
    )
    monkeypatch.setattr(
        "apps.operations.managed_live.transaction.on_commit",
        lambda callback: callback(),
    )

    assert monitor_managed_live(management.pk) == "monitored"
    management.refresh_from_db()
    assert management.state == ManagedLiveTrade.State.ACTIVE
    assert management.initial_quantity == Decimal("1")
    assert management.remaining_quantity == Decimal("1")
    assert management.breakeven_moved is True
    assert management.effective_stop == Decimal("100")
    assert sum(
        (target.allocated_quantity for target in management.targets.all()),
        Decimal("0"),
    ) == Decimal("1")
    assert not queued

    price["value"] = Decimal("120")
    assert monitor_managed_live(management.pk) == "monitored"
    management.refresh_from_db()
    assert management.high_water == Decimal("120")
    assert management.effective_stop == Decimal("118.8")
    assert not queued

    price["value"] = Decimal("118")
    assert monitor_managed_live(management.pk) == "full_exit_queued"
    management.refresh_from_db()
    assert management.state == ManagedLiveTrade.State.EXITING
    sells = LiveSpotOrder.objects.filter(side="sell")
    assert sells.count() == 1
    exit_order = sells.get()
    assert exit_order.order_type == "market"
    assert exit_order.amount == Decimal("1")
    assert len(queued) == 1

    # A repeated monitor pass cannot create or enqueue a duplicate exit.
    assert monitor_managed_live(management.pk) == ManagedLiveTrade.State.EXITING
    assert LiveSpotOrder.objects.filter(side="sell").count() == 1
    assert len(queued) == 1


@pytest.mark.django_db
@override_settings(LIVE_TRADING_ENABLED=True)
def test_stage27_managed_live_fixed_tp_then_trailing_sl_protects_remainder(
    monkeypatch, django_user_model
):
    owner = django_user_model.objects.create_user(username="stage27-managed-fixed-tp")
    account = live_account(owner)
    market = spot_market(account)
    plan = ready_live_plan(
        owner,
        account,
        market,
        trailing=False,
        trailing_sl=True,
        trigger="tp1",
    )
    entry = LiveSpotOrder.objects.create(
        owner=owner,
        account=account,
        market=market,
        request_key=uuid.uuid4(),
        client_order_id="stage27-fixed-entry",
        external_order_id="provider-fixed-entry",
        side="buy",
        order_type="limit",
        amount=Decimal("1"),
        price=Decimal("100"),
        filled_amount=Decimal("1"),
        average_price=Decimal("100"),
        state=LiveSpotOrder.State.FILLED,
    )
    management = create_managed_live(owner, plan.pk, entry)
    price = {"value": Decimal("110")}
    monkeypatch.setattr(
        "apps.operations.managed_live.refresh_live_quote",
        lambda market: {
            "status": "ok",
            "data": {"price": str(price["value"]), "stale": False},
        },
    )
    monkeypatch.setattr(
        "apps.operations.managed_live._provider_free_base",
        lambda item: Decimal("10"),
    )
    monkeypatch.setattr(
        "apps.operations.managed_live.transaction.on_commit",
        lambda callback: None,
    )

    assert monitor_managed_live(management.pk) == "tp1_exit_queued"
    management.refresh_from_db()
    assert management.breakeven_moved is True
    assert management.effective_stop == Decimal("100")
    tp1 = management.targets.get(position=1)
    assert tp1.state == "exit_pending"
    assert tp1.exit_order is not None
    assert tp1.exit_order.amount == Decimal("0.1")

    tp1.exit_order.state = LiveSpotOrder.State.FILLED
    tp1.exit_order.filled_amount = Decimal("0.1")
    tp1.exit_order.average_price = Decimal("110")
    tp1.exit_order.save()
    price["value"] = Decimal("109")
    assert monitor_managed_live(management.pk) == "monitored"
    management.refresh_from_db()
    assert management.remaining_quantity == Decimal("0.9")
    assert management.effective_stop == Decimal("100")



@pytest.mark.django_db
@override_settings(LIVE_TRADING_ENABLED=True)
def test_stage27_live_order_api_binds_ready_plan_to_managed_trade(
    client, django_user_model, monkeypatch
):
    password = "stage27-managed-api-password"
    owner = django_user_model.objects.create_user(
        username="stage27-managed-api",
        password=password,
    )
    account = live_account(owner)
    market = spot_market(account)
    plan = ready_live_plan(owner, account, market)
    queued = []
    monkeypatch.setattr(
        "apps.core.react_views.live_spot_order.apply_async",
        lambda args, queue: queued.append((args, queue)),
    )
    monkeypatch.setattr(
        "apps.core.react_views.transaction.on_commit",
        lambda callback: callback(),
    )
    client.force_login(owner)
    step = client.post(
        reverse("api-step-up"),
        data=json.dumps({"password": password}),
        content_type="application/json",
    )
    assert step.status_code == 200
    response = client.post(
        reverse("api-live-orders"),
        data=json.dumps(
            {
                "account": account.pk,
                "market": market.pk,
                "side": "buy",
                "amount": "1.000",
                "price": "100",
                "confirmed": True,
                "plan_id": plan.pk,
                "plan_revision": plan.revision,
                "request_key": str(uuid.uuid4()),
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    order = LiveSpotOrder.objects.get(pk=response.json()["order"]["id"])
    management = ManagedLiveTrade.objects.get(entry_order=order)
    assert management.plan_id == plan.pk
    assert management.state == ManagedLiveTrade.State.PENDING_ENTRY
    assert management.trailing_enabled is True
    assert management.trailing_sl_enabled is True
    assert management.trailing_trigger == "tp2"
    assert management.targets.count() == 3
    assert queued == [([order.pk], "orders")]


@pytest.mark.django_db
@override_settings(LIVE_TRADING_ENABLED=True)
def test_stage27_protective_exit_executes_while_new_entries_are_paused(
    monkeypatch, django_user_model
):
    owner = django_user_model.objects.create_user(username="stage27-protective-pause")
    account = live_account(owner)
    market = spot_market(account)
    plan = ready_live_plan(owner, account, market)
    entry = LiveSpotOrder.objects.create(
        owner=owner,
        account=account,
        market=market,
        request_key=uuid.uuid4(),
        client_order_id="stage27-pause-entry",
        external_order_id="entry-filled",
        side="buy",
        order_type="limit",
        amount=Decimal("1"),
        price=Decimal("100"),
        filled_amount=Decimal("1"),
        average_price=Decimal("100"),
        state=LiveSpotOrder.State.FILLED,
    )
    management = create_managed_live(owner, plan.pk, entry)
    management.initial_quantity = Decimal("1")
    management.remaining_quantity = Decimal("1")
    management.state = ManagedLiveTrade.State.EXITING
    management.save()
    exit_order = LiveSpotOrder.objects.create(
        owner=owner,
        account=account,
        market=market,
        request_key=uuid.uuid4(),
        client_order_id="stage27-pause-protective-exit",
        side="sell",
        order_type="market",
        amount=Decimal("1"),
        price=None,
        state=LiveSpotOrder.State.PENDING,
    )
    ManagedLiveExit.objects.create(
        management=management,
        reason="stop_or_trailing",
        order=exit_order,
    )
    AccountControl.objects.create(account=account, paused=True, reason="operator_pause")

    class FakeAdapter:
        def validate_credentials(self):
            class Permission:
                safe_for_trading = True

            return Permission()

        def place_order(self, **intent):
            return Order(
                order_id="protective-provider-order",
                client_order_id=intent["client_order_id"],
                symbol=intent["symbol"],
                side=intent["side"],
                order_type=intent["order_type"],
                amount=intent["amount"],
                price=intent["price"],
                filled_amount=intent["amount"],
                average_price=Decimal("99"),
                status=OrderStatus.FILLED,
                created_at=datetime.now(UTC),
            )

    monkeypatch.setattr(
        "apps.exchanges.live_orders.get_account_credentials",
        lambda account: {},
    )
    monkeypatch.setattr(
        "apps.exchanges.live_orders.get_adapter",
        lambda *args, **kwargs: FakeAdapter(),
    )
    result = execute_live_spot_order(exit_order.pk)
    assert result["status"] == LiveSpotOrder.State.FILLED
    exit_order.refresh_from_db()
    assert exit_order.state == LiveSpotOrder.State.FILLED



@pytest.mark.django_db
def test_stage27_account_market_api_returns_searchable_spot_markets(
    client, django_user_model
):
    owner = django_user_model.objects.create_user(username="stage27-market-api")
    account = live_account(owner)
    spot_market(account, "BTC/USDT")
    spot_market(account, "ETH/USDT")
    client.force_login(owner)
    response = client.get(
        reverse("api-account-markets", args=[account.pk])
    )
    assert response.status_code == 200, response.content
    symbols = {row["symbol"] for row in response.json()["markets"]}
    assert {"BTC/USDT", "ETH/USDT"}.issubset(symbols)



@pytest.mark.django_db
def test_stage27_signal_edit_then_approve_transfer_contract(
    client, django_user_model
):
    owner = django_user_model.objects.create_user(username="stage27-signal-transfer")
    account = live_account(owner)
    market = spot_market(account)
    source = SignalSource.objects.create(
        owner=owner,
        name="Stage27 smart paste",
        method=SignalSource.Method.SMART_PASTE,
    )
    raw = RawSignal.objects.create(
        owner=owner,
        source=source,
        original_text=(
            "BTCUSDT LONG ENTRY 80000 "
            "TP1 82000 TP2 84000 TP3 86000 SL 78000"
        ),
        original_payload={},
        checksum="stage27-transfer-contract",
    )
    signal = Signal.objects.create(
        owner=owner,
        source=source,
        raw_signal=raw,
        exchange_account=account,
        market=market,
        side="long",
        entry_price=Decimal("80000"),
        stop_loss=Decimal("78000"),
        technical_confidence=100,
        parser_version="rules-v2",
        parsed_payload={
            "parser_version": "rules-v2",
            "pair": "BTC/USDT",
            "trailing_defaults": {
                "trailing_sl": True,
                "percentage_trailing": True,
                "percentage_trigger": "tp1",
                "percentage_distance": "1",
            },
        },
        status=Signal.Status.PARSED,
    )
    SignalTarget.objects.bulk_create(
        [
            SignalTarget(
                signal=signal,
                position=1,
                price=Decimal("82000"),
                share_percent=Decimal("10"),
            ),
            SignalTarget(
                signal=signal,
                position=2,
                price=Decimal("84000"),
                share_percent=Decimal("10"),
            ),
            SignalTarget(
                signal=signal,
                position=3,
                price=Decimal("86000"),
                share_percent=Decimal("80"),
            ),
        ]
    )

    client.force_login(owner)
    detail = client.get(reverse("api-inbox-detail", args=[signal.pk]))
    assert detail.status_code == 200, detail.content
    revision = detail.json()["signal"]["revision"]

    edited = client.post(
        reverse("api-inbox-edit", args=[signal.pk]),
        data=json.dumps(
            {
                "account_id": account.pk,
                "market_id": market.pk,
                "side": "long",
                "entry_price": "80000",
                "stop_loss": "78000",
                "tp1": "82000",
                "tp2": "84000",
                "tp3": "86000",
                "revision": revision,
                "reason": "",
            }
        ),
        content_type="application/json",
    )
    assert edited.status_code == 200, edited.content
    saved = edited.json()["signal"]
    assert saved["status"] == Signal.Status.PARSED
    assert saved["revision"] == revision + 1

    approved = client.post(
        reverse("api-inbox-action", args=[signal.pk]),
        data=json.dumps(
            {
                "revision": saved["revision"],
                "action": "approve",
                "reason": "",
            }
        ),
        content_type="application/json",
    )
    assert approved.status_code == 200, approved.content
    result = approved.json()["signal"]
    assert result["status"] == Signal.Status.APPROVED
    structured = result["structured"]
    assert structured["account_id"] == account.pk
    assert structured["market_id"] == market.pk
    assert structured["entry"] == "80000"
    assert structured["stop_loss"] == "78000"
    assert [row["price"] for row in structured["targets"]] == [
        "82000",
        "84000",
        "86000",
    ]
