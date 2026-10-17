"""Real database dashboard accounting, freshness, isolation and query budget."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from apps.exchanges.models import BalanceSnapshot, UserExchangeAccount
from apps.operations.models import ExternalObservation
from apps.portfolio.balances import balances_for
from apps.portfolio.metrics import day_bounds, summarize, trade_queryset
from apps.portfolio.views import dashboard_context
from apps.trading.exits_engine import process_paper_price
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from redis.exceptions import ConnectionError
from test_stages09_exits import paper_trade


def quote(market, price="65000", age=0):
    cache.set(
        f"marketdata:v1:quote:{market.pk}",
        {
            "price": price,
            "observed_at": (timezone.now() - timedelta(seconds=age)).isoformat(),
            "source": "simulator",
        },
        60,
    )


@pytest.mark.django_db
def test_balance_total_available_wallet_scope_and_missing_rate(django_user_model):
    user = django_user_model.objects.create_user(username="valuation13")
    trade = paper_trade(user)
    account = UserExchangeAccount.objects.select_related("exchange").get(pk=trade.account_id)
    quote(trade.market)
    cards, ok = balances_for([account], "USDT")
    assert ok and len(cards) == 1
    rows = {r["asset"]: r for r in cards[0]["rows"]}
    assert rows["USDT"]["total"] == rows["USDT"]["free"] + rows["USDT"]["locked"]
    assert rows["USDT"]["reserved"] == 0  # Consumed entry is deducted, not reserved twice.
    assert rows["BTC"]["total"] >= trade.quantity
    BalanceSnapshot.objects.create(
        exchange_account=account,
        asset=trade.market.base_asset,
        free_balance=10,
        locked_balance=5,
        total_balance=15,
        captured_at=timezone.now(),
        wallet_scope="margin",
    )
    cards, _ = balances_for([account], "USDT")
    assert cards[0]["complete"] is False
    margin = next(r for r in cards[0]["rows"] if r["wallet"] == "margin")
    assert margin["total"] == 15 and margin["value"] is None
    quote(trade.market, age=40)
    cards, _ = balances_for([account], "USDT")
    assert next(r for r in cards[0]["rows"] if r["asset"] == "BTC")["value"] is None


@pytest.mark.django_db
def test_net_pnl_partial_then_closed_includes_all_fees(django_user_model):
    user = django_user_model.objects.create_user(username="pnl13")
    trade = paper_trade(user, two=True)
    process_paper_price(trade.pk, price="70000", event_key="pnl-target")
    quote(trade.market, "71000")
    data = summarize(user, trade_queryset(user))
    stats = data["trades"][0].stats
    entries = list(trade.orders.get().fills.all())
    exits = list(trade.exit_fills.all())
    cost = sum(f.quantity * f.price for f in entries)
    fees = sum(f.fee for f in entries)
    qty = sum(f.quantity for f in entries)
    expected = sum(
        f.quantity * (f.price - cost / qty) - f.fee - fees * f.quantity / qty for f in exits
    )
    assert stats["realized"] == expected
    assert stats["remaining"] == qty - sum(f.quantity for f in exits)
    assert data["buckets"][0]["closed"] == 0
    process_paper_price(trade.pk, price="59000", event_key="pnl-stop")
    stats = summarize(user, trade_queryset(user))["trades"][0].stats
    proceeds = sum(f.quantity * f.price - f.fee for f in trade.exit_fills.all())
    assert abs(stats["realized"] - (proceeds - cost - fees)) < Decimal("0.000000000001")
    assert stats["unrealized"] == 0 and stats["remaining"] == 0


@pytest.mark.django_db
def test_today_uses_user_midnight_and_future_quote_rejected(django_user_model):
    user = django_user_model.objects.create_user(username="day13", timezone="Asia/Tehran")
    start, end = day_bounds(user)
    assert start.hour == end.hour == 0 and start.utcoffset().total_seconds() == 12600
    trade = paper_trade(user)
    quote(trade.market, age=-60)
    data = summarize(user, trade_queryset(user))
    assert data["trades"][0].stats["unrealized"] is None
    assert data["buckets"][0]["unpriced_open"] == 1


@pytest.mark.django_db
def test_dashboard_endpoints_external_privacy_empty_and_query_budget(
    client, django_user_model, record_property
):
    owner = django_user_model.objects.create_user(username="dash13")
    other = django_user_model.objects.create_user(username="private13")
    trade = paper_trade(owner)
    external = ExternalObservation.objects.create(
        account=trade.account,
        kind="order",
        external_id="read-only",
        payload={"api_key": "never-browser", "symbol": "BTCUSDT"},
    )
    client.force_login(owner)
    assert client.get("/dashboard/").status_code == 200
    with CaptureQueriesContext(connection) as queries:
        context = dashboard_context(owner, {})
    record_property("dashboard_queries", len(queries))
    record_property("dashboard_build_ms", context["build_ms"])
    assert len(queries) <= 28
    fragment = client.get("/dashboard/panels/")
    assert fragment.status_code == 200, fragment.content
    assert b"never-browser" not in fragment.content
    assert client.get("/api/v1/dashboard/").status_code == 200
    assert b"never-browser" not in client.get(f"/external/{external.pk}/").content
    client.force_login(other)
    assert client.get(f"/external/{external.pk}/").status_code == 404
    assert client.get(f"/api/v1/dashboard/?account={trade.account_id}").status_code == 404
    assert client.get("/dashboard/panels/").status_code == 200
    assert client.post("/api/v1/dashboard/").status_code == 405


@pytest.mark.django_db
def test_cache_failure_preserves_counts_and_labels_unpriced(django_user_model):
    owner = django_user_model.objects.create_user(username="offline13")
    paper_trade(owner)
    with patch("apps.portfolio.quotes.cache.get_many", side_effect=ConnectionError()):
        context = dashboard_context(owner, {})
    assert context["cache_ok"] is False
    assert context["open_count"] == 1
    assert context["buckets"][0]["unpriced_open"] == 1
