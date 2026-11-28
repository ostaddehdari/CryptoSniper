"""Stage27 market chart markers and public-price freshness."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from apps.exchanges.adapters import Ticker
from apps.marketdata.models import HistoricalCandle
from apps.marketdata.views import HEADER_TICKER_CACHE_KEY, _header_ticker_value
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from test_stage23_signal_inbox import make_signal
from test_trading_stage08 import paper_account


@pytest.mark.django_db
def test_ticker_uses_source_time_units_and_marks_fallback_stale(monkeypatch):
    cache.delete(HEADER_TICKER_CACHE_KEY)
    cache.delete(HEADER_TICKER_CACHE_KEY + ":stale")
    now = timezone.now()

    class Adapter:
        def __init__(self, code):
            self.code = code

        def fetch_ticker(self, symbol):
            return Ticker(symbol, Decimal("117000" if self.code == "nobitex" else "1.0001"), now)

    monkeypatch.setattr("apps.marketdata.views.get_adapter", lambda code, **kw: Adapter(code))
    first = _header_ticker_value()
    assert first["usdt_toman"] == "117000"
    assert first["units"]["usdt_toman"] == "IRT (تومان)"
    assert first["source_times"]["usdt_toman"] == now.isoformat()
    cache.delete(HEADER_TICKER_CACHE_KEY)

    class StaleAdapter(Adapter):
        def fetch_ticker(self, symbol):
            return Ticker(symbol, Decimal("9999999"), now - timedelta(hours=1))

    monkeypatch.setattr("apps.marketdata.views.get_adapter", lambda code, **kw: StaleAdapter(code))
    with patch("apps.marketdata.views.timezone.now", return_value=now):
        fallback = _header_ticker_value()
    assert fallback["stale"] is True
    assert fallback["usdt_toman"] == "117000"


@pytest.mark.django_db
def test_chart_levels_hit_markers_and_stale_quote_never_pretends_live(client, django_user_model):
    owner = django_user_model.objects.create_user(username="s27-chart")
    account, market = paper_account(owner)
    signal = make_signal(owner, status="parsed", account=account, market=market)
    now = timezone.now()
    t1, t2 = now - timedelta(minutes=10), now - timedelta(minutes=5)
    type(signal).objects.filter(pk=signal.pk).update(created_at=now - timedelta(minutes=11))
    for moment, lo, hi, close in (
        (t1, "64000", "66000", "65000"),
        (t2, "69000", "71000", "70000"),
    ):
        HistoricalCandle.objects.create(
            provider="binance_public",
            symbol=market.symbol,
            interval="5m",
            open_time=moment,
            close_time=moment + timedelta(minutes=5),
            open_price=close,
            high_price=hi,
            low_price=lo,
            close_price=close,
            volume="1",
        )
    client.force_login(owner)
    with (
        patch(
            "apps.marketdata.chart.get_quote",
            return_value={
                "price": "999999",
                "source": "fake",
                "observed_at": t1.isoformat(),
                "stale": True,
            },
        ),
        patch("apps.marketdata.chart.refresh_quote", return_value={"status": "unavailable"}),
    ):
        payload = client.get(
            reverse("api-market-chart") + f"?market={market.pk}&signal={signal.pk}&bars=30"
        ).json()
    assert payload["quote"]["stale"] is True
    assert len(payload["candles"]) == 2
    assert {row["kind"] for row in payload["overlay"]["levels"]} == {"entry", "tp1", "sl"}
    markers = {row["kind"]: row["time"] for row in payload["overlay"]["markers"]}
    assert markers["entry"] == int(t1.timestamp())
    assert markers["tp1"] == int(t2.timestamp())
