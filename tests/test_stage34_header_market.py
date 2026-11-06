from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from apps.exchanges.adapters import InvalidProviderResponse, Ticker
from apps.marketdata import views
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone


@pytest.fixture(autouse=True)
def clear_header_cache():
    with override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    ):
        cache.clear()
        yield
        cache.clear()


def quote(value, source, label, status="live"):
    return {
        "value": value,
        "source": source,
        "source_label": label,
        "observed_at": timezone.now().isoformat(),
        "age_seconds": 0,
        "status": status,
    }


@pytest.mark.django_db
def test_header_returns_nobitex_toman_and_btc_usdt(client, django_user_model):
    user = django_user_model.objects.create_user(username="stage34-header")
    client.force_login(user)
    results = {
        "nobitex": quote("118500", "nobitex_public", "نوبیتکس"),
        "binance": quote("68123.45", "binance_public", "Binance"),
    }
    with patch("apps.marketdata.views._quote_payload", side_effect=lambda code, *_: results[code]):
        response = client.get(reverse("api-header-ticker"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["quotes"]["usdt_toman"]["value"] == "118500"
    assert payload["quotes"]["usdt_toman"]["source"] == "nobitex_public"
    assert payload["quotes"]["btc_usdt"]["value"] == "68123.45"
    assert payload["refresh_after_seconds"] == 5
    assert payload["stale"] is False
    assert payload["display_only"] is True


def test_header_keeps_last_good_quote_and_marks_only_failed_source_stale():
    first = {
        "nobitex": quote("118500", "nobitex_public", "نوبیتکس"),
        "binance": quote("68123.45", "binance_public", "Binance"),
    }
    with patch("apps.marketdata.views._quote_payload", side_effect=lambda code, *_: first[code]):
        views._header_ticker_value()

    cache.delete(views.HEADER_TICKER_CACHE_KEY)

    def refresh(code, *_):
        if code == "nobitex":
            raise InvalidProviderResponse("provider_connection_failed")
        return quote("68130.10", "binance_public", "Binance")

    with patch("apps.marketdata.views._quote_payload", side_effect=refresh):
        payload = views._header_ticker_value()

    assert payload["quotes"]["usdt_toman"]["value"] == "118500"
    assert payload["quotes"]["usdt_toman"]["status"] == "stale"
    assert payload["quotes"]["btc_usdt"]["value"] == "68130.10"
    assert payload["quotes"]["btc_usdt"]["status"] == "live"
    assert payload["stale"] is True


def test_provider_timestamp_older_than_limit_is_not_reported_live():
    adapter = SimpleNamespace(
        fetch_ticker=lambda symbol: Ticker(
            symbol,
            Decimal("118500"),
            timezone.now() - timedelta(seconds=views.HEADER_QUOTE_STALE_SECONDS + 1),
        )
    )
    with patch("apps.marketdata.views.get_adapter", return_value=adapter):
        payload = views._quote_payload("nobitex", "USDT/IRT", "نوبیتکس")
    assert payload["status"] == "stale"
    assert payload["age_seconds"] > views.HEADER_QUOTE_STALE_SECONDS
