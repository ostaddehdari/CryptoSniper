import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.exchanges.models import LiveSpotOrder
from apps.marketdata.models import HistoricalCandle
from apps.operations.models import ExternalObservation
from apps.signals.models import RawSignal, Signal, SignalSource
from test_stage27_workflow import live_account, spot_market


@pytest.mark.django_db
def test_stage28_trade_archive_filters_internal_and_external(client, django_user_model):
    owner = django_user_model.objects.create_user(username="stage28-archive")
    account = live_account(owner)
    market = spot_market(account)
    order = LiveSpotOrder.objects.create(
        owner=owner,
        account=account,
        market=market,
        client_order_id="stage28-order",
        side="buy",
        order_type="limit",
        amount=Decimal("1"),
        price=Decimal("100"),
        state=LiveSpotOrder.State.OPEN,
    )
    external = ExternalObservation.objects.create(
        account=account,
        kind="order",
        external_id="BTCUSDT:stage28",
        payload={
            "symbol": "BTCUSDT",
            "side": "buy",
            "origQty": "1",
            "price": "100",
            "status": "open",
        },
    )
    client.force_login(owner)

    for source, item in (("internal", order), ("external", external)):
        response = client.post(
            reverse("api-trade-archive"),
            data=json.dumps({"source": source, "id": item.pk, "archived": True}),
            content_type="application/json",
        )
        assert response.status_code == 200, response.content

    active = client.get(reverse("api-live-orders"))
    assert active.status_code == 200
    assert active.json()["orders"] == []
    assert active.json()["external"] == []

    archived = client.get(reverse("api-live-orders") + "?view=archive").json()
    assert [row["id"] for row in archived["orders"]] == [order.pk]
    assert [row["id"] for row in archived["external"]] == [external.pk]

    all_rows = client.get(reverse("api-live-orders") + "?view=all").json()
    assert [row["id"] for row in all_rows["orders"]] == [order.pk]
    assert [row["id"] for row in all_rows["external"]] == [external.pk]


@pytest.mark.django_db
def test_stage28_signal_archive_restore_and_default_active_filter(client, django_user_model):
    owner = django_user_model.objects.create_user(username="stage28-signal-archive")
    source = SignalSource.objects.create(
        owner=owner,
        name="manual",
        method=SignalSource.Method.MANUAL,
    )
    raw = RawSignal.objects.create(
        owner=owner,
        source=source,
        original_text="BTCUSDT LONG ENTRY 100 TP1 110 SL 90",
        original_payload={},
        checksum="stage28-signal-archive",
    )
    signal = Signal.objects.create(owner=owner, source=source, raw_signal=raw)
    client.force_login(owner)

    response = client.post(
        reverse("api-inbox-action", args=[signal.pk]),
        data=json.dumps({"action": "delete"}),
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["archived"] is True
    assert client.get(reverse("api-inbox-list")).json()["items"] == []
    archived = client.get(reverse("api-inbox-list") + "?view=archive").json()["items"]
    assert [row["id"] for row in archived] == [signal.pk]

    restored = client.post(
        reverse("api-inbox-action", args=[signal.pk]),
        data=json.dumps({"action": "restore"}),
        content_type="application/json",
    )
    assert restored.status_code == 200
    assert restored.json()["archived"] is False
    assert [row["id"] for row in client.get(reverse("api-inbox-list")).json()["items"]] == [
        signal.pk
    ]


@pytest.mark.django_db
def test_stage28_market_candles_support_short_timeframes_and_live_payload(
    client, django_user_model, monkeypatch
):
    owner = django_user_model.objects.create_user(username="stage28-candles")
    account = live_account(owner)
    market = spot_market(account)
    now = timezone.now()
    HistoricalCandle.objects.create(
        provider="binance_public",
        symbol=market.symbol,
        interval="1m",
        open_time=now - timedelta(minutes=2),
        close_time=now - timedelta(minutes=1),
        open_price=Decimal("100"),
        high_price=Decimal("103"),
        low_price=Decimal("99"),
        close_price=Decimal("102"),
        volume=Decimal("12"),
    )
    monkeypatch.setattr("apps.core.react_views.fetch_binance_history", lambda *a, **k: 0)
    monkeypatch.setattr(
        "apps.core.react_views.get_quote",
        lambda market: {"price": "102.5", "stale": False},
    )
    client.force_login(owner)
    response = client.get(reverse("api-market-candles", args=[market.pk]) + "?interval=1m")
    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["interval"] == "1m"
    assert payload["quote"]["price"] == "102.5"
    assert payload["candles"][0]["open"] == "100.0000000000000000"
    assert payload["history_source"] == "binance_public"


@pytest.mark.django_db
def test_stage28_manual_sync_refreshes_external_observations(monkeypatch, django_user_model):
    owner = django_user_model.objects.create_user(username="stage28-sync")
    account = live_account(owner)
    observed = []

    monkeypatch.setattr(
        "apps.exchanges.tasks.run_sync",
        lambda account: {"market_count": 1, "balance_count": 1},
    )
    monkeypatch.setattr(
        "apps.operations.external.observe_account",
        lambda account: observed.append(account.pk)
        or {"status": "read_only_snapshot", "open_orders": 1, "history": 2},
    )

    from apps.exchanges.tasks import sync_exchange_account

    result = sync_exchange_account.run(account.pk)
    assert observed == [account.pk]
    assert result["external"]["open_orders"] == 1
    assert result["external"]["history"] == 2


def test_stage28_react_source_contains_live_chart_markers_archive_and_real_refresh():
    source = (
        Path(__file__).parents[1] / "frontend-react" / "src" / "main.jsx"
    ).read_text()
    for token in (
        "deriveHitMarkers",
        "CandleSvg",
        "eventLine",
        "eventPoint",
        "نمایش خطوط معامله باز",
        'view=active',
        "/api/v1/trades/archive/",
        "تازه‌سازی واقعی",
        "SignalSchematic",
        "کارتی",
        "جدولی",
    ):
        assert token in source
