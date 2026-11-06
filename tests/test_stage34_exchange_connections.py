from decimal import Decimal

import pytest
from apps.exchanges.adapters import (
    Balance,
    InvalidProviderResponse,
    Market,
    PermissionReport,
    TradingFee,
)
from apps.exchanges.forms import ExchangeConnectionForm
from apps.exchanges.models import Exchange, ExchangeMarket, UserExchangeAccount
from apps.exchanges.security import get_account_credentials, revoke_account_credentials
from apps.exchanges.services import sync_exchange_account
from django.urls import reverse


def connection_form(owner, exchange, key="key", secret="secret"):
    return ExchangeConnectionForm(
        owner,
        {
            "exchange": exchange.pk,
            "environment": "live",
            "api_key": key,
            "api_secret": secret,
            "no_withdrawal_confirmed": "on",
            "ip_restricted_confirmed": "on",
        },
    )


@pytest.mark.django_db
def test_deleted_connection_is_reactivated_with_automatic_name(django_user_model):
    owner = django_user_model.objects.create_user(username="stage34-reconnect")
    exchange = Exchange.objects.get(code="lbank")
    first = connection_form(owner, exchange, key="old-key")
    assert first.is_valid(), first.errors
    account = first.save()
    assert account.label == "LBank"
    original_id = account.pk

    revoke_account_credentials(account)
    replacement = connection_form(owner, exchange, key="new-key")
    assert replacement.is_valid(), replacement.errors
    account = replacement.save()

    assert account.pk == original_id
    assert account.label == "LBank"
    assert account.status == UserExchangeAccount.Status.PENDING
    assert get_account_credentials(account)["api_key"] == "new-key"
    assert UserExchangeAccount.objects.filter(owner=owner, exchange=exchange).count() == 1


@pytest.mark.django_db
def test_provider_failure_leaves_actionable_error_instead_of_pending(
    django_user_model, monkeypatch
):
    owner = django_user_model.objects.create_user(username="stage34-sync-error")
    exchange = Exchange.objects.get(code="nobitex")
    form = connection_form(owner, exchange, key="token", secret="")
    assert form.is_valid(), form.errors
    account = form.save()

    class BrokenNobitex:
        def validate_credentials(self):
            raise InvalidProviderResponse("nobitex_invalid_profile")

    monkeypatch.setattr(
        "apps.exchanges.services.get_adapter", lambda *args, **kwargs: BrokenNobitex()
    )
    with pytest.raises(InvalidProviderResponse):
        sync_exchange_account(account)

    account.refresh_from_db()
    assert account.status == UserExchangeAccount.Status.ERROR
    assert account.trading_enabled is False
    assert account.last_error_code == "sync.permissions.nobitex_invalid_profile"
    assert "مجوز" in account.last_error_message
    assert account.last_error_at is not None


@pytest.mark.django_db
def test_sync_refreshes_permissions_account_fee_and_zero_free_usdt(django_user_model, monkeypatch):
    owner = django_user_model.objects.create_user(username="stage34-sync-complete")
    exchange = Exchange.objects.get(code="lbank")
    form = connection_form(owner, exchange)
    assert form.is_valid(), form.errors
    account = form.save()

    class HealthyLbank:
        def validate_credentials(self):
            return PermissionReport(True, True, False, False, True, "account-7")

        def fetch_markets(self):
            return [
                Market(
                    "BTC/USDT",
                    "BTC",
                    "USDT",
                    "spot",
                    min_amount=Decimal("0.0001"),
                    amount_step=Decimal("0.0001"),
                    price_step=Decimal("0.01"),
                    min_notional=Decimal("10"),
                )
            ]

        def fetch_trading_fees(self):
            return [TradingFee("BTC/USDT", Decimal("0.001"), Decimal("0.002"))]

        def fetch_balance(self):
            return [Balance("USDT", Decimal("0"), Decimal("0"))]

    monkeypatch.setattr(
        "apps.exchanges.services.get_adapter", lambda *args, **kwargs: HealthyLbank()
    )
    result = sync_exchange_account(account)

    account.refresh_from_db()
    market = ExchangeMarket.objects.get(exchange=exchange, symbol="BTC/USDT")
    balance = account.balance_snapshots.get(asset__symbol="USDT")
    assert result["status"] == UserExchangeAccount.Status.CONNECTED
    assert result["fee_count"] == 1
    assert account.permissions["can_trade_spot"] is True
    assert account.last_error_code == ""
    assert market.maker_fee == Decimal("0.001")
    assert market.taker_fee == Decimal("0.002")
    assert market.metadata["fee_source"] == "account_api"
    assert balance.free_balance == Decimal("0")


@pytest.mark.django_db
def test_react_create_ignores_manual_label_and_returns_automatic_name(
    client, django_user_model, monkeypatch
):
    owner = django_user_model.objects.create_user(username="stage34-create-api")
    exchange = Exchange.objects.get(code="lbank")
    queued = []
    monkeypatch.setattr(
        "apps.exchanges.tasks.sync_exchange_account.apply_async",
        lambda args, queue: queued.append((args, queue)),
    )
    client.force_login(owner)
    response = client.post(
        reverse("api-exchange-create"),
        {
            "exchange": exchange.pk,
            "label": "نام دستی نباید ذخیره شود",
            "api_key": "key",
            "api_secret": "secret",
            "no_withdrawal_confirmed": True,
            "ip_restricted_confirmed": True,
        },
        content_type="application/json",
    )

    assert response.status_code == 201, response.content
    assert response.json()["label"] == "LBank"
    account = UserExchangeAccount.objects.get(owner=owner)
    assert account.label == "LBank"
    assert queued == [([account.pk], "maintenance")]
