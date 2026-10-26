from decimal import Decimal
from uuid import uuid4

import pytest
from apps.exchanges.live_orders import queue_live_spot_order
from apps.exchanges.models import (
    BalanceSnapshot,
    ExchangeMarket,
    LiveSpotOrder,
    UserExchangeAccount,
)
from apps.exchanges.security import revoke_account_credentials
from apps.exchanges.services import sync_exchange_account
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from kombu.exceptions import OperationalError
from test_exchange_sync import create_simulator_account


@pytest.mark.django_db
def test_disabled_or_revoked_connections_are_hidden_from_center_system_and_api(
    client, django_user_model
):
    user = django_user_model.objects.create_user(username="s23-hidden-exchange")
    account = create_simulator_account(user)
    sync_exchange_account(account)
    client.force_login(user)
    center = client.get(reverse("exchange-center"))
    system = client.get(reverse("system"))
    assert center.status_code == system.status_code == 200
    assert b'id="root"' in center.content and b'id="root"' in system.content
    revoke_account_credentials(account)
    accounts = client.get(reverse("api-exchanges")).json()["accounts"]
    assert all(row["id"] != account.pk for row in accounts)


@pytest.mark.django_db
def test_add_exchange_does_not_white_screen_when_broker_is_down(
    client, django_user_model, monkeypatch
):
    user = django_user_model.objects.create_user(username="s23-broker-down")
    from apps.exchanges.models import Exchange

    exchange = Exchange.objects.get(code="simulator")
    monkeypatch.setattr(
        "apps.exchanges.views.sync_exchange_account.apply_async",
        lambda *args, **kwargs: (_ for _ in ()).throw(OperationalError("broker down")),
    )
    client.force_login(user)
    response = client.post(
        reverse("exchange-account-add"),
        {"exchange": exchange.pk, "label": "Broker safe", "environment": "paper"},
    )
    assert response.status_code == 302
    account = UserExchangeAccount.objects.get(owner=user, label="Broker safe")
    assert response["Location"].endswith(f"/exchanges/{account.pk}/")


@pytest.mark.django_db
@override_settings(LIVE_TRADING_ENABLED=True)
def test_live_boundary_rejects_stale_balance_and_bad_precision(django_user_model):
    user = django_user_model.objects.create_user(username="s23-live-boundary")
    account = create_simulator_account(user)
    sync_exchange_account(account)
    account.environment = "live"
    account.status = "connected"
    account.trading_enabled = True
    account.permissions = {
        "can_read": True,
        "can_trade_spot": True,
        "can_trade_margin": False,
        "can_withdraw": False,
    }
    account.save()
    market = ExchangeMarket.objects.get(
        exchange=account.exchange, symbol="BTC/USDT", market_type="spot"
    )
    with pytest.raises(ValidationError):
        queue_live_spot_order(
            user,
            account,
            {
                "request_key": uuid4(),
                "market": market,
                "side": "buy",
                "amount": Decimal("0.0000015"),
                "price": Decimal("65000"),
            },
        )
    account.balance_snapshots.all().delete()
    with pytest.raises(ValidationError):
        queue_live_spot_order(
            user,
            account,
            {
                "request_key": uuid4(),
                "market": market,
                "side": "buy",
                "amount": Decimal("0.001"),
                "price": Decimal("65000"),
            },
        )


@pytest.mark.django_db
@override_settings(LIVE_TRADING_ENABLED=True)
def test_live_order_is_durable_pending_before_provider_execution(django_user_model):
    user = django_user_model.objects.create_user(username="s23-live-durable")
    account = create_simulator_account(user)
    sync_exchange_account(account)
    account.environment = "live"
    account.status = "connected"
    account.trading_enabled = True
    account.permissions = {
        "can_read": True,
        "can_trade_spot": True,
        "can_trade_margin": False,
        "can_withdraw": False,
    }
    account.save()
    market = ExchangeMarket.objects.get(
        exchange=account.exchange, symbol="BTC/USDT", market_type="spot"
    )
    BalanceSnapshot.objects.filter(exchange_account=account, asset=market.quote_asset).update(
        captured_at=timezone.now()
    )
    order, created = queue_live_spot_order(
        user,
        account,
        {
            "request_key": uuid4(),
            "market": market,
            "side": "buy",
            "amount": Decimal("0.001"),
            "price": Decimal("65000"),
        },
    )
    assert created
    assert order.state == LiveSpotOrder.State.PENDING
