from decimal import Decimal

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from apps.exchanges.adapters import Ticker
from apps.exchanges.models import Asset, Exchange, ExchangeMarket, UserExchangeAccount
from apps.marketdata.feeds import get_live_quote, refresh_live_quote


class FakeAdapter:
    def __init__(self, prices=None):
        self.prices = prices or {"BTC/USDT": Decimal("84000"), "USDT/IRT": Decimal("120000")}

    def fetch_ticker(self, symbol):
        return Ticker(symbol=symbol, price=self.prices[symbol], observed_at=timezone.now())


@pytest.mark.django_db
def test_stage26_direct_live_quote_short_cache(monkeypatch):
    exchange = Exchange.objects.get(code="bitunix")
    btc, _ = Asset.objects.get_or_create(symbol="BTC")
    usdt, _ = Asset.objects.get_or_create(symbol="USDT")
    market, _ = ExchangeMarket.objects.update_or_create(
        exchange=exchange,
        symbol="BTC/USDT",
        market_type="spot",
        defaults={
            "base_asset": btc,
            "quote_asset": usdt,
            "active": True,
            "max_leverage": Decimal("1"),
        },
    )
    cache.clear()
    monkeypatch.setattr("apps.marketdata.feeds.get_adapter", lambda *a, **k: FakeAdapter())
    result = refresh_live_quote(market)
    assert result["status"] == "ok"
    quote = get_live_quote(market)
    assert quote["price"] == "84000"
    assert quote["source"] == "bitunix"
    assert quote["live"] is True
    assert quote["stale"] is False


@pytest.mark.django_db
def test_stage26_public_header_prices_are_explicit_sources(client, django_user_model, monkeypatch):
    owner = django_user_model.objects.create_user(username="stage26-live")
    client.force_login(owner)
    cache.clear()
    monkeypatch.setattr("apps.marketdata.views.get_adapter", lambda *a, **k: FakeAdapter())
    response = client.get(reverse("api-public-prices"))
    assert response.status_code == 200
    prices = response.json()["prices"]
    assert prices["btc_usdt"]["price"] == "84000"
    assert prices["btc_usdt"]["source"] == "bitunix"
    assert prices["usdt_irt"]["price"] == "120000"
    assert prices["usdt_irt"]["source"] == "nobitex"


@pytest.mark.django_db
def test_stage26_authenticated_live_market_endpoint(client, django_user_model, monkeypatch):
    owner = django_user_model.objects.create_user(username="stage26-market")
    exchange = Exchange.objects.get(code="bitunix")
    btc, _ = Asset.objects.get_or_create(symbol="BTC")
    usdt, _ = Asset.objects.get_or_create(symbol="USDT")
    market, _ = ExchangeMarket.objects.update_or_create(
        exchange=exchange,
        symbol="BTC/USDT",
        market_type="spot",
        defaults={
            "base_asset": btc,
            "quote_asset": usdt,
            "active": True,
            "max_leverage": Decimal("1"),
        },
    )
    UserExchangeAccount.objects.create(
        owner=owner,
        exchange=exchange,
        label="live",
        environment="live",
        status="connected",
        permissions={"can_read": True, "can_trade_spot": True, "can_withdraw": False},
        trading_enabled=True,
    )
    cache.clear()
    monkeypatch.setattr("apps.marketdata.feeds.get_adapter", lambda *a, **k: FakeAdapter())
    client.force_login(owner)
    response = client.get(reverse("api-market-quotes"), {"market": market.pk, "live": "1"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["live"] is True
    assert payload["markets"][0]["quote"]["price"] == "84000"
