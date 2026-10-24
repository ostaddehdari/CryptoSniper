import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from apps.marketdata.models import HistoricalCandle
from apps.operations.models import ExternalObservation
from apps.signals.archive import archive_expired_signals
from apps.signals.models import RawSignal, Signal, SignalOutcome, SignalSource
from django.urls import reverse
from django.utils import timezone
from test_stages09_exits import paper_trade


def make_signal(user, market=None):
    source = SignalSource.objects.create(owner=user, name="stage24", method="manual")
    raw = RawSignal.objects.create(
        owner=user,
        source=source,
        original_text="BTC long",
        original_payload={},
        checksum="a" * 64,
    )
    return Signal.objects.create(
        owner=user,
        source=source,
        raw_signal=raw,
        market=market,
        side="long" if market else "",
        entry_price="65000" if market else None,
        stop_loss="60000" if market else None,
        status="parsed" if market else "new",
    )


@pytest.mark.django_db
def test_stage24_app_shell_and_archive_filters(client, django_user_model):
    user = django_user_model.objects.create_user(username="s24-shell")
    signal = make_signal(user)
    client.force_login(user)

    page = client.get(reverse("app-shell"))
    assert page.status_code == 200
    assert b"stage24-app.js" in page.content
    assert b"stage24-app.css" in page.content
    assert b'data-page="inbox"' in page.content
    assert b'data-page="newtrade"' in page.content
    assert b'data-page="trades"' in page.content

    active = client.get(reverse("api-inbox") + "?view=active").json()["items"]
    assert [row["id"] for row in active] == [signal.pk]
    archived = client.post(
        reverse("api-inbox-archive", args=[signal.pk]),
        data=json.dumps({"archived": True}),
        content_type="application/json",
    )
    assert archived.status_code == 200
    assert client.get(reverse("api-inbox") + "?view=active").json()["items"] == []
    assert client.get(reverse("api-inbox") + "?view=archive").json()["items"][0]["id"] == signal.pk


@pytest.mark.django_db
def test_expired_signal_is_auto_archived(django_user_model):
    user = django_user_model.objects.create_user(username="s24-expire")
    signal = make_signal(user)
    now = timezone.now()
    SignalOutcome.objects.create(
        signal=signal,
        owner=user,
        status=SignalOutcome.Status.EXPIRED,
        symbol="BTC/USDT",
        evaluated_from=now - timedelta(hours=3),
        evaluated_until=now,
    )
    assert archive_expired_signals(owner=user) == 1
    signal.refresh_from_db()
    assert signal.archived_at is not None


@pytest.mark.django_db
def test_unified_trades_include_internal_external_and_archive(client, django_user_model):
    user = django_user_model.objects.create_user(username="s24-trades")
    trade = paper_trade(user)
    external = ExternalObservation.objects.create(
        account=trade.account,
        kind="history",
        external_id="BTCUSDT:s24",
        payload={
            "symbol": "BTCUSDT",
            "side": "buy",
            "status": "filled",
            "avgPrice": "65000",
            "executedQty": "0.002",
        },
    )
    client.force_login(user)
    payload = client.get(reverse("api-stage24-trades") + "?view=active").json()
    keys = {row["key"] for row in payload["trades"]}
    assert f"paper:{trade.pk}" in keys
    assert f"external:{external.pk}" in keys

    response = client.post(
        reverse("api-stage24-trades-archive"),
        data=json.dumps({"kind": "paper", "id": trade.pk, "archived": True}),
        content_type="application/json",
    )
    assert response.status_code == 200
    active_keys = {
        row["key"]
        for row in client.get(reverse("api-stage24-trades") + "?view=active").json()["trades"]
    }
    assert f"paper:{trade.pk}" not in active_keys
    archive_keys = {
        row["key"]
        for row in client.get(reverse("api-stage24-trades") + "?view=archive").json()["trades"]
    }
    assert f"paper:{trade.pk}" in archive_keys


@pytest.mark.django_db
def test_refresh_endpoint_runs_real_read_sync_boundary(client, django_user_model):
    user = django_user_model.objects.create_user(username="s24-refresh")
    paper_trade(user)
    client.force_login(user)
    with (
        patch(
            "apps.portfolio.api_stage24.run_account_sync",
            return_value={"market_count": 1, "balance_count": 2},
        ) as sync,
        patch(
            "apps.portfolio.api_stage24.observe_external_account",
            return_value="read_only_snapshot",
        ) as observe,
    ):
        response = client.post(
            reverse("api-stage24-trades-refresh"),
            data="{}",
            content_type="application/json",
        )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["trades"]
    sync.assert_called()
    observe.assert_called()


@pytest.mark.django_db
def test_chart_returns_candles_and_trade_overlay(client, django_user_model):
    user = django_user_model.objects.create_user(username="s24-chart")
    trade = paper_trade(user, three=True)
    now = timezone.now()
    HistoricalCandle.objects.create(
        provider="binance_public",
        symbol=trade.market.symbol,
        interval="5m",
        open_time=now - timedelta(minutes=5),
        close_time=now,
        open_price="64000",
        high_price="71000",
        low_price="63000",
        close_price="70000",
        volume="12",
    )
    client.force_login(user)
    with patch("apps.marketdata.chart.fetch_binance_history", return_value=0):
        response = client.get(
            reverse("api-market-chart")
            + f"?market={trade.market_id}&trade={trade.pk}&interval=5m&bars=30"
        )
    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["candles"]
    assert payload["overlay"]["type"] == "internal_trade"
    kinds = {row["kind"] for row in payload["overlay"]["levels"]}
    assert {"entry", "tp1", "tp2", "tp3", "sl"} <= kinds
