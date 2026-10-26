from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from apps.accounts.models import TradingPreferences
from apps.accounts.security import STEP_UP_SESSION_KEY
from apps.exchanges.models import (
    Asset,
    BalanceSnapshot,
    Exchange,
    ExchangeMarket,
    LiveSpotOrder,
    UserExchangeAccount,
)
from apps.marketdata.models import ExchangeFavorite
from apps.operations.models import AccountControl
from apps.tradeplans.forms import ManualTradeForm
from apps.tradeplans.models import TradePlan
from apps.tradeplans.service import approve_plan, create_draft
from apps.tradeplans.submission import submit
from django.db import connection, connections
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone


@pytest.fixture
def workspace(django_user_model):
    owner = django_user_model.objects.create_user(username="s30-owner")
    exchange = Exchange.objects.create(
        code="s30", name="S30 Exchange", adapter_code="s30-test", enabled=True, spot_supported=True
    )
    btc, _ = Asset.objects.get_or_create(symbol="BTC")
    usdt, _ = Asset.objects.get_or_create(symbol="USDT")
    account = UserExchangeAccount.objects.create(
        owner=owner,
        exchange=exchange,
        label="Main",
        environment="live",
        status="connected",
        trading_enabled=True,
        permissions={"can_read": True, "can_trade_spot": True, "can_withdraw": False},
    )
    market = ExchangeMarket.objects.create(
        exchange=exchange,
        symbol="BTC/USDT",
        base_asset=btc,
        quote_asset=usdt,
        market_type="spot",
        min_amount=Decimal("0.001"),
        amount_step=Decimal("0.001"),
        price_step=Decimal("0.01"),
        min_notional=Decimal("10"),
        max_leverage=Decimal("1"),
        taker_fee=Decimal("0.001"),
        synced_at=timezone.now(),
    )
    BalanceSnapshot.objects.create(
        exchange_account=account,
        asset=usdt,
        wallet_scope="spot",
        free_balance=Decimal("1000"),
        total_balance=Decimal("1000"),
        captured_at=timezone.now(),
    )
    return owner, account, market


def body(account, market, **changes):
    result = {
        "account": str(account.pk),
        "market": str(market.pk),
        "source": "manual",
        "side": "long",
        "entry_price": "100",
        "stop_loss": "95",
        "tp1": "110",
        "tp2": "120",
        "tp3": "130",
        "capital": "200",
        "leverage": "1",
        "trailing_sl": True,
        "percentage_trailing": True,
        "trailing_trigger": "tp1",
        "trailing_distance": "1",
        "request_key": str(uuid4()),
        "confirmed": True,
    }
    result.update(changes)
    return result


def login_step_up(client, owner):
    client.force_login(owner)
    session = client.session
    session[STEP_UP_SESSION_KEY] = timezone.now().isoformat()
    session.save()


@pytest.mark.django_db
def test_markets_are_paginated_beyond_old_cap_and_scoped(client, workspace, django_user_model):
    owner, account, market = workspace
    coins = Asset.objects.bulk_create([Asset(symbol=f"Z{i:04}") for i in range(1100)])
    ExchangeMarket.objects.bulk_create(
        [
            ExchangeMarket(
                exchange=account.exchange,
                symbol=f"{c.symbol}/USDT",
                base_asset=c,
                quote_asset=market.quote_asset,
                market_type="spot",
                max_leverage=1,
            )
            for c in coins
        ]
    )
    client.force_login(owner)
    url = reverse("api-account-markets", args=[account.pk])
    seen, offset = set(), 0
    while offset is not None:
        r = client.get(url, {"limit": 200, "offset": offset})
        assert r.status_code == 200
        page = r.json()
        assert page["total"] == 1101
        ids = {x["id"] for x in page["markets"]}
        assert not seen & ids
        seen |= ids
        offset = page["next_offset"]
    assert len(seen) == 1101
    assert client.get(url, {"q": "Z1099"}).json()["markets"][0]["base"] == "Z1099"
    assert client.get(url, {"market_id": "wrong"}).status_code == 400
    assert client.get(url, {"offset": -1}).status_code == 400
    other = django_user_model.objects.create_user(username="s30-other")
    client.force_login(other)
    assert client.get(url).status_code == 404


@pytest.mark.django_db
def test_favorite_order_is_per_exchange_and_handles_multiple_accounts(client, workspace):
    owner, account, market = workspace
    UserExchangeAccount.objects.create(
        owner=owner, exchange=account.exchange, label="Second", status="connected"
    )
    eth, _ = Asset.objects.get_or_create(symbol="ETH")
    ExchangeMarket.objects.create(
        exchange=account.exchange,
        symbol="ETH/USDT",
        base_asset=eth,
        quote_asset=market.quote_asset,
        market_type="spot",
    )
    client.force_login(owner)
    url = reverse("api-ui-favorites")
    r = client.post(
        url, {"exchange": "s30", "symbols": ["ETH", "BTC"]}, content_type="application/json"
    )
    assert r.status_code == 200, r.content
    assert client.get(url, {"exchange": "s30"}).json()["symbols"] == ["ETH", "BTC"]
    rows = client.get(reverse("api-account-markets", args=[account.pk])).json()["markets"]
    assert [x["base"] for x in rows] == ["ETH", "BTC"]
    assert all(x["favorite"] for x in rows)
    assert (
        client.post(
            url, {"exchange": "s30", "symbols": ["ABSENT"]}, content_type="application/json"
        ).status_code
        == 400
    )
    assert list(ExchangeFavorite.objects.filter(owner=owner).values_list("symbol", flat=True)) == [
        "ETH",
        "BTC",
    ]
    assert client.get(url, {"exchange": "binance"}).status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize("risk,capital", [("1", "200"), ("2", "400")])
def test_fix_loss_uses_free_usdt_and_matches_approved_examples(client, workspace, risk, capital):
    owner, account, market = workspace
    BalanceSnapshot.objects.create(
        exchange_account=account,
        asset=market.quote_asset,
        wallet_scope="margin",
        free_balance=Decimal("9000"),
        total_balance=Decimal("9000"),
        captured_at=timezone.now(),
    )
    client.force_login(owner)
    r = client.post(
        reverse("api-fix-loss"),
        {
            "account_id": account.pk,
            "market_id": market.pk,
            "entry": "100",
            "stop": "95",
            "risk_percent": risk,
        },
        content_type="application/json",
    )
    assert r.status_code == 200, r.content
    data = r.json()
    assert data["available"] == "1000.0000000000000000"
    assert data["suggested_capital"] == capital
    assert Decimal(data["estimated_stop_loss"]) <= Decimal(data["risk_budget"])
    assert data["advisory_only"] and not data["fees_in_risk_budget"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "changes",
    [
        {"entry": "NaN"},
        {"stop": "Infinity"},
        {"stop": "105"},
        {"leverage": "3"},
        {"side": "short"},
        {"risk_percent": "0"},
        {"risk_percent": "21"},
        {"entry": "1e-99999"},
    ],
)
def test_fix_loss_rejects_invalid_values(client, workspace, changes):
    owner, account, market = workspace
    client.force_login(owner)
    data = {
        "account_id": account.pk,
        "market_id": market.pk,
        "entry": "100",
        "stop": "95",
        **changes,
    }
    assert (
        client.post(reverse("api-fix-loss"), data, content_type="application/json").status_code
        == 400
    )


@pytest.mark.django_db
def test_fix_loss_rejects_stale_balance(client, workspace):
    owner, account, market = workspace
    account.balance_snapshots.update(captured_at=timezone.now() - timedelta(minutes=16))
    client.force_login(owner)
    r = client.post(
        reverse("api-fix-loss"),
        {"account_id": account.pk, "market_id": market.pk, "entry": "100", "stop": "95"},
        content_type="application/json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_saved_defaults_are_integer_and_snapshot_shares_survive_preference_changes(
    client, workspace
):
    owner, account, market = workspace
    prefs = TradingPreferences.objects.create(
        owner=owner,
        tp1_percent=20,
        tp2_percent=30,
        tp3_percent=50,
        trailing_trigger="tp2",
        trailing_distance_percent=2,
    )
    data = body(account, market, tp3=None)
    data["client_token"] = data["request_key"]
    form = ManualTradeForm(owner, data)
    assert form.is_valid(), form.errors
    plan, _ = create_draft(owner, form.cleaned_data)
    prefs.tp1_percent, prefs.tp2_percent, prefs.tp3_percent = 10, 10, 80
    prefs.save()
    plan = approve_plan(owner, plan.pk, plan.revision)
    assert [t["share_percent"] for t in plan.approved_snapshot["targets"]] == ["20", "80"]
    client.force_login(owner)
    p = client.get(reverse("api-trading-preferences")).json()["trading_preferences"]
    assert p["trailing_distance_percent"] == "2"
    assert p["tp_distribution"] == ["10", "10", "80"]


@pytest.mark.django_db
@override_settings(LIVE_TRADING_ENABLED=True)
def test_atomic_submission_uses_server_quantity_and_stable_key(client, workspace, monkeypatch):
    owner, account, market = workspace
    login_step_up(client, owner)
    queued = []
    monkeypatch.setattr("apps.tradeplans.submission._dispatch", lambda pk: queued.append(pk))
    data = body(account, market, amount="999999")
    with TestCase.captureOnCommitCallbacks(execute=True):
        first = client.post(reverse("api-manual-submit"), data, content_type="application/json")
    assert first.status_code == 201, first.content
    second = client.post(reverse("api-manual-submit"), data, content_type="application/json")
    assert second.status_code == 200, second.content
    assert first.json()["order"]["id"] == second.json()["order"]["id"]
    order = LiveSpotOrder.objects.get()
    assert order.amount == Decimal(order.source_plan.approved_snapshot["quantity"])
    assert order.amount == Decimal("1.998")
    assert order.source_plan.status == "ready"
    assert order.source_plan.trailing_sl and order.source_plan.percentage_trailing
    assert len(queued) == 1
    rows = client.get(reverse("api-stage24-trades")).json()["trades"]
    row = next(x for x in rows if x["key"] == f"live:{order.pk}")
    assert row["plan_id"] == order.source_plan_id
    assert Decimal(row["stop_loss"]) == Decimal("95")
    assert [Decimal(x) for x in row["tp"]] == [Decimal("110"), Decimal("120"), Decimal("130")]
    assert row["automatic_exits_active"] is False
    conflict = client.post(
        reverse("api-manual-submit"), {**data, "capital": "300"}, content_type="application/json"
    )
    assert conflict.status_code == 400
    assert LiveSpotOrder.objects.count() == TradePlan.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("reason", ["gate", "paused", "unconfirmed", "step_up", "precision"])
def test_failed_submission_never_leaves_partial_plan_or_order(client, workspace, reason, settings):
    owner, account, market = workspace
    settings.LIVE_TRADING_ENABLED = reason != "gate"
    login_step_up(client, owner)
    data = body(account, market)
    if reason == "paused":
        AccountControl.objects.create(account=account, paused=True)
    if reason == "unconfirmed":
        data["confirmed"] = False
    if reason == "step_up":
        session = client.session
        session.pop(STEP_UP_SESSION_KEY)
        session.save()
    if reason == "precision":
        data["entry_price"] = "100.001"
    r = client.post(reverse("api-manual-submit"), data, content_type="application/json")
    assert r.status_code in (400, 403), r.content
    assert not LiveSpotOrder.objects.exists()
    assert not TradePlan.objects.exists()


@pytest.mark.django_db(transaction=True)
@override_settings(LIVE_TRADING_ENABLED=True)
def test_concurrent_duplicate_submit_creates_one_plan_and_one_order(workspace, monkeypatch):
    owner, account, market = workspace
    data = body(account, market)
    key = uuid4()
    data["client_token"] = str(key)
    form = ManualTradeForm(owner, data)
    assert form.is_valid(), form.errors
    monkeypatch.setattr("apps.tradeplans.submission._dispatch", lambda pk: None)
    barrier = Barrier(2)

    def run():
        try:
            barrier.wait(timeout=10)
            order, _ = submit(owner, dict(form.cleaned_data), key)
            return order.pk
        finally:
            connections.close_all()

    assert connection.vendor == "postgresql"
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(lambda _: run(), range(2)))
    assert a == b
    assert LiveSpotOrder.objects.count() == TradePlan.objects.count() == 1
