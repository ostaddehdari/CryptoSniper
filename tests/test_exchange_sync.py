import json

import pytest
from apps.exchanges.models import BalanceSnapshot, Exchange, ExchangeMarket, UserExchangeAccount
from apps.exchanges.security import set_account_credentials
from apps.exchanges.services import sync_exchange_account
from django.urls import reverse


def create_simulator_account(owner, label="تمرین من"):
    exchange = Exchange.objects.get(code="simulator")
    account = UserExchangeAccount(
        owner=owner,
        exchange=exchange,
        label=label,
        environment=UserExchangeAccount.Environment.PAPER,
    )
    set_account_credentials(account, {})
    account.save()
    return account


@pytest.mark.django_db
def test_simulator_sync_persists_permissions_markets_and_balance(django_user_model):
    owner = django_user_model.objects.create_user(username="sync-owner")
    account = create_simulator_account(owner)
    result = sync_exchange_account(account)
    account.refresh_from_db()
    assert result["status"] == UserExchangeAccount.Status.CONNECTED
    assert account.permissions["can_withdraw"] is False
    assert account.trading_enabled
    assert ExchangeMarket.objects.filter(exchange=account.exchange, active=True).count() == 3
    assert BalanceSnapshot.objects.filter(exchange_account=account).count() == 3
    btc_spot = ExchangeMarket.objects.get(
        exchange=account.exchange, symbol="BTC/USDT", market_type="spot"
    )
    assert str(btc_spot.min_notional) == "10.0000000000000000"


@pytest.mark.django_db
def test_exchange_pages_are_owner_scoped_and_api_never_returns_ciphertext(
    client, django_user_model
):
    owner = django_user_model.objects.create_user(username="ui-owner")
    other = django_user_model.objects.create_user(username="ui-other")
    account = create_simulator_account(owner)
    sync_exchange_account(account)
    client.force_login(owner)
    assert client.get(reverse("exchange-center")).status_code == 200
    detail = client.get(reverse("exchange-account-detail", args=[account.pk]))
    assert detail.status_code == 200
    assert "BTC/USDT" in detail.content.decode()
    api = client.get(reverse("api-exchanges"))
    assert api.status_code == 200
    serialized = json.dumps(api.json())
    assert "credentials_encrypted" not in serialized
    assert account.credentials_encrypted not in serialized
    client.force_login(other)
    assert client.get(reverse("exchange-account-detail", args=[account.pk])).status_code == 404
    assert client.get(reverse("api-exchange-account", args=[account.pk])).status_code == 404


@pytest.mark.django_db
def test_add_simulator_ignores_supplied_secret_and_disable_is_immediate(
    client, django_user_model, monkeypatch
):
    owner = django_user_model.objects.create_user(username="form-owner")
    exchange = Exchange.objects.get(code="simulator")
    queued = []
    monkeypatch.setattr(
        "apps.exchanges.views.sync_exchange_account.apply_async",
        lambda args, queue: queued.append((args, queue)),
    )
    client.force_login(owner)
    response = client.post(
        reverse("exchange-account-add"),
        {
            "exchange": exchange.pk,
            "label": "دموی من",
            "environment": "live",
            "api_key": "must-be-ignored",
            "api_secret": "must-be-ignored-too",
            "passphrase": "must-be-ignored-too",
        },
    )
    account = UserExchangeAccount.objects.get(owner=owner)
    assert response.status_code == 302
    assert account.environment == "paper"
    assert "must-be-ignored" not in account.credentials_encrypted
    assert queued == [([account.pk], "maintenance")]
    disable = client.post(reverse("exchange-account-disable", args=[account.pk]))
    assert disable.status_code == 302
    account.refresh_from_db()
    assert account.status == "disabled"
    assert not account.trading_enabled


@pytest.mark.django_db
def test_live_sync_cannot_reenable_paused_trading(django_user_model):
    from apps.operations.models import AccountControl
    from django.test import override_settings

    owner = django_user_model.objects.create_user(username="sync-live-pause")
    account = create_simulator_account(owner)
    account.environment = UserExchangeAccount.Environment.LIVE
    account.save(update_fields=["environment", "updated_at"])
    with override_settings(LIVE_TRADING_ENABLED=False):
        sync_exchange_account(account)
    account.refresh_from_db()
    assert account.status == UserExchangeAccount.Status.CONNECTED
    assert not account.trading_enabled

    control = AccountControl.objects.create(account=account, paused=True, reason="stage25_cutover")
    with override_settings(LIVE_TRADING_ENABLED=True):
        sync_exchange_account(account)
    account.refresh_from_db()
    assert not account.trading_enabled

    control.paused = False
    control.save(update_fields=["paused", "updated_at"])
    with override_settings(LIVE_TRADING_ENABLED=True):
        sync_exchange_account(account)
    account.refresh_from_db()
    assert account.trading_enabled
