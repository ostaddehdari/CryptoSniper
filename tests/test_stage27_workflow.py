import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.exchanges.adapters import Order, OrderStatus
from apps.exchanges.live_orders import reconcile_live_spot_order
from apps.exchanges.models import (
    Asset,
    BalanceSnapshot,
    Exchange,
    ExchangeMarket,
    LiveSpotOrder,
    UserExchangeAccount,
)
from apps.operations.external_management import adopt_or_update, monitor_one
from apps.operations.models import ExternalObservation, ExternalTradeManagement
from apps.signals.models import RawSignal, Signal, SignalSource


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
        reverse("api-security-step-up"),
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
    assert structured["entry"] == "80000.0000000000000000"
    assert structured["stop_loss"] == "78000.0000000000000000"
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
    client.force_login(owner)
    step = client.post(
        reverse("api-security-step-up"),
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
