# fmt: off
import hashlib
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
    assert "js/pwa.js" in body
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
        adapter_code="react_test_adapter",
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
        adapter_code="market_test_adapter",
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



@pytest.mark.django_db
@pytest.mark.parametrize(
    ("route_name", "page"),
    [
        ("exchange-center", "exchanges"),
        ("watchlists", "watchlist"),
        ("alerts", "alerts"),
        ("reports", "reports"),
        ("operations", "operations"),
        ("system", "operations"),
        ("profile", "settings"),
        ("trading-preferences", "settings"),
        ("sessions", "settings"),
        ("audit-events", "settings"),
        ("source-settings", "settings"),
        ("telegram-settings", "telegram"),
        ("manual-list", "plans"),
        ("manual-new", "manual"),
        ("inbox", "inbox"),
        ("smart-paste", "smart"),
        ("notifications", "alerts"),
        ("external-list", "trades"),
        ("paper-trades", "trades"),
    ],
)
def test_visible_legacy_routes_render_same_react_workspace(
    client, django_user_model, route_name, page
):
    user = django_user_model.objects.create_user(username=f"react-route-{route_name}")
    client.force_login(user)

    response = client.get(reverse(route_name))

    assert response.status_code == 200
    body = response.content.decode()
    assert 'id="root"' in body
    assert "static/react/app.js" in body
    assert "stage24-rebuild.css" not in body
    assert f'window.__CS_INITIAL_PAGE__="{page}"' in body


@pytest.mark.django_db
def test_react_exchange_catalog_uses_real_ids_and_does_not_hide_binance(
    client, django_user_model
):
    user = django_user_model.objects.create_user(username="react-exchange-catalog")
    exchange, _ = Exchange.objects.get_or_create(
        code="binance",
        defaults={
            "name": "Binance",
            "adapter_code": "react_binance_test",
            "enabled": True,
            "spot_supported": True,
        },
    )
    if not exchange.enabled:
        exchange.enabled = True
        exchange.save(update_fields=("enabled",))
    client.force_login(user)

    response = client.get(reverse("api-exchanges"))

    assert response.status_code == 200
    rows = response.json()["exchanges"]
    row = next(item for item in rows if item["code"] == "binance")
    assert row["id"] == exchange.pk

    root = Path(__file__).resolve().parents[1]
    source = (root / "frontend-react/src/main.jsx").read_text()
    assert 'filter(x=>x.code!=="binance")' not in source
    assert "catalog[0]?.id" in source



def test_approved_react_visual_base_is_byte_locked():
    root = Path(__file__).resolve().parents[1]
    data = (root / "frontend-react/src/styles.css").read_bytes()
    git_blob = hashlib.sha1(
        f"blob {len(data)}\0".encode() + data,
        usedforsecurity=False,
    ).hexdigest()
    assert git_blob == "565980a9a4a5ba390f09fcc61c5a6ea9a6a82cdd"


def test_react_shell_keeps_approved_sidebar_topbar_and_navigation_contract():
    root = Path(__file__).resolve().parents[1]
    source = (root / "frontend-react/src/main.jsx").read_text()
    for fragment in (
        'className={"sidebar "+(collapsed?"collapsed":"")}',
        'className="brand"',
        'className="logoMark"',
        'className="collapseBtn"',
        'className={"navItem "+(page===id?"active":"")}',
        'className="sidebarFoot"',
        'className="topbar"',
        'className="content"',
    ):
        assert fragment in source

    for label in (
        "نمای کلی",
        "معاملات",
        "معامله دستی",
        "برنامه‌های معامله",
        "تحلیل سیگنال",
        "صندوق سیگنال",
        "صرافی‌ها",
        "کیف پول‌ها و راهنما",
        "دیده‌بان و بازارها",
        "تلگرام و سیگنال‌ها",
        "هشدارها",
        "گزارش‌ها",
        "وضعیت سیستم",
        "تنظیمات",
    ):
        assert label in source


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
    assert ".s24-" not in styles
    assert "stage24-rebuild" not in source
# fmt: on
