from pathlib import Path

import pytest
from apps.exchanges.models import Asset, Exchange, ExchangeMarket, UserExchangeAccount
from django.urls import reverse


@pytest.mark.django_db
def test_primary_surface_is_real_react_app(client, django_user_model):
    user = django_user_model.objects.create_user(username="react-primary")
    client.force_login(user)

    response = client.get(reverse("home"))

    assert response.status_code == 200
    body = response.content.decode()
    assert 'id="root"' in body
    assert "static/react/app.js" in body
    assert "static/react/app.css" in body
    assert "stage24-rebuild.css" not in body
    assert 'class="s24-shell"' not in body
    assert 'window.__CS_BASE__' in body


@pytest.mark.django_db
def test_react_bootstrap_exposes_real_non_simulator_accounts(
    client, django_user_model
):
    user = django_user_model.objects.create_user(username="react-bootstrap")
    exchange = Exchange.objects.create(
        code="reactx",
        name="React Exchange",
        adapter_code="lbank",
        enabled=True,
        spot_supported=True,
    )
    account = UserExchangeAccount.objects.create(
        owner=user,
        exchange=exchange,
        label="Main",
        environment=UserExchangeAccount.Environment.LIVE,
        status=UserExchangeAccount.Status.CONNECTED,
        permissions={"can_read": True, "can_withdraw": False},
    )
    client.force_login(user)

    response = client.get(reverse("api-ui-bootstrap"))

    assert response.status_code == 200
    accounts = response.json()["accounts"]
    assert any(row["id"] == account.pk for row in accounts)


@pytest.mark.django_db
def test_react_account_market_picker_returns_markets_immediately(
    client, django_user_model
):
    user = django_user_model.objects.create_user(username="react-markets")
    exchange = Exchange.objects.create(
        code="marketx",
        name="Market Exchange",
        adapter_code="bitunix",
        enabled=True,
        spot_supported=True,
    )
    btc = Asset.objects.create(symbol="BTC")
    usdt = Asset.objects.create(symbol="USDT")
    market = ExchangeMarket.objects.create(
        exchange=exchange,
        symbol="BTC/USDT",
        base_asset=btc,
        quote_asset=usdt,
        market_type=ExchangeMarket.MarketType.SPOT,
    )
    account = UserExchangeAccount.objects.create(
        owner=user,
        exchange=exchange,
        label="Main",
        environment=UserExchangeAccount.Environment.LIVE,
        status=UserExchangeAccount.Status.CONNECTED,
        permissions={"can_read": True, "can_withdraw": False},
    )
    client.force_login(user)

    response = client.get(reverse("api-account-markets", args=[account.pk]))

    assert response.status_code == 200
    payload = response.json()
    assert payload["account"]["id"] == account.pk
    assert any(row["id"] == market.pk for row in payload["markets"])


def test_react_source_contains_full_workspace_and_no_legacy_shell_contract():
    root = Path(__file__).resolve().parents[1]
    source = (root / "frontend-react/src/main.jsx").read_text()
    styles = (root / "frontend-react/src/styles.css").read_text()

    for component in (
        "function Dashboard",
        "function Trades",
        "function Manual",
        "function ManualPlans",
        "function SmartPaste",
        "function SignalInbox",
        "function Exchanges",
        "function Wallets",
        "function Watchlist",
        "function Telegram",
        "function Alerts",
        "function Reports",
        "function Operations",
        "function SettingsPage",
    ):
        assert component in source

    assert 'className={"sidebar "' in source
    assert 'className="topbar"' in source
    assert ".sidebar{" in styles
    assert ".topbar{" in styles
    assert "s24-shell" not in source
