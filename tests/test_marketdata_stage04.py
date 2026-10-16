from datetime import timedelta
from decimal import Decimal

import pytest
from apps.exchanges.models import Exchange, ExchangeMarket, UserExchangeAccount
from apps.exchanges.security import set_account_credentials
from apps.exchanges.services import sync_exchange_account
from apps.marketdata.feeds import _key, get_quote, refresh_quote
from apps.marketdata.models import Watchlist, WatchlistItem
from apps.marketdata.search import search_markets
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone


def simulator_account(user):
    exchange = Exchange.objects.get(code="simulator")
    account = UserExchangeAccount(owner=user, exchange=exchange, label="Demo", environment="paper")
    set_account_credentials(account, {})
    account.save()
    sync_exchange_account(account)
    return account


@pytest.mark.django_db
def test_public_simulator_quote_is_display_only_and_stales(django_user_model):
    user = django_user_model.objects.create_user(username="market-feed")
    account = simulator_account(user)
    market = ExchangeMarket.objects.get(
        exchange=account.exchange, symbol="BTC/USDT", market_type="spot"
    )
    result = refresh_quote(market)
    assert result["status"] == "ok"
    assert Decimal(result["data"]["price"]) > 0
    assert result["data"]["trade_eligible"] is False
    old = cache.get(_key(market.pk))
    old["observed_at"] = (timezone.now() - timedelta(seconds=40)).isoformat()
    cache.set(_key(market.pk), old, 90)
    assert get_quote(market)["stale"] is True
    assert get_quote(market)["trade_eligible"] is False


@pytest.mark.django_db
def test_watchlist_account_scope_csrf_and_disconnected_visibility(client, django_user_model):
    owner = django_user_model.objects.create_user(username="market-owner")
    other = django_user_model.objects.create_user(username="market-other")
    account = simulator_account(owner)
    market = ExchangeMarket.objects.get(
        exchange=account.exchange, symbol="BTC/USDT", market_type="spot"
    )
    client.force_login(owner)
    page = client.get(reverse("watchlists"))
    assert page.status_code == 200
    wl = Watchlist.objects.get(owner=owner)
    assert (
        client.post(reverse("watchlist-add", args=[wl.pk]), {"market_id": market.pk}).status_code
        == 302
    )
    item = WatchlistItem.objects.get(watchlist=wl)
    payload = client.get(reverse("api-watchlist", args=[wl.pk])).json()
    assert payload["items"][0]["market_id"] == market.pk
    assert payload["display_only"] is True
    client.force_login(other)
    assert client.get(reverse("api-watchlist", args=[wl.pk])).status_code == 404
    assert client.post(reverse("watchlist-remove", args=[wl.pk, item.pk])).status_code == 404
    assert (
        client.get(reverse("api-market-quotes") + "?market=" + str(market.pk)).json()["markets"]
        == []
    )
    assert search_markets(other, "BTC") == []


@pytest.mark.django_db
def test_invalid_market_query_rejected_and_no_credentials_leak(client, django_user_model):
    user = django_user_model.objects.create_user(username="market-api")
    simulator_account(user)
    client.force_login(user)
    assert client.get(reverse("api-market-quotes") + "?market=abc").status_code == 400
    results = client.get(reverse("api-market-search") + "?q=BTC").json()["results"]
    assert any(item["symbol"] == "BTC/USDT" for item in results)
    assert all("credentials" not in item and "secret" not in item for item in results)
    assert client.get(reverse("api-market-stream")).status_code == 409


@pytest.mark.django_db
def test_refresh_task_guard_and_missing_market(client, django_user_model, monkeypatch):
    user = django_user_model.objects.create_user(username="market-refresh")
    account = simulator_account(user)
    market = ExchangeMarket.objects.get(
        exchange=account.exchange, symbol="ETH/USDT", market_type="spot"
    )
    client.force_login(user)
    wl = Watchlist.objects.create(owner=user, name="تست")
    queued = []
    monkeypatch.setattr(
        "apps.marketdata.watchlists.refresh_market.apply_async",
        lambda **kwargs: queued.append(kwargs),
    )
    url = reverse("watchlist-refresh", args=[wl.pk, market.pk])
    assert client.get(url).status_code == 405
    assert client.post(url).status_code == 302
    assert len(queued) == 1
    assert queued[0]["queue"] == "maintenance"
