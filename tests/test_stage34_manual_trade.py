from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from apps.exchanges.adapters import Balance
from apps.exchanges.models import (
    Asset,
    BalanceSnapshot,
    Exchange,
    ExchangeMarket,
    UserExchangeAccount,
)
from apps.marketdata.feeds import _key
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone


@pytest.fixture
def manual_workspace(django_user_model):
    owner = django_user_model.objects.create_user(username="stage34-manual")
    exchange = Exchange.objects.create(
        code="s34", name="Stage34", adapter_code="s34-adapter", enabled=True
    )
    btc = Asset.objects.create(symbol="BTC")
    usdt = Asset.objects.create(symbol="USDT")
    account = UserExchangeAccount.objects.create(
        owner=owner,
        exchange=exchange,
        label="Main",
        environment="live",
        status="connected",
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
    return owner, account, market


@pytest.mark.django_db
def test_manual_quote_refreshes_selected_market_immediately(client, manual_workspace):
    owner, _account, market = manual_workspace
    client.force_login(owner)

    def refresh(selected):
        cache.set(
            _key(selected.pk),
            {
                "market_id": selected.pk,
                "exchange": selected.exchange.code,
                "symbol": selected.symbol,
                "market_type": selected.market_type,
                "price": "68123.45",
                "bid": "68123.40",
                "ask": "68123.50",
                "bids": [["68123.40", "1"]],
                "asks": [["68123.50", "1"]],
                "observed_at": timezone.now().isoformat(),
                "source": "s34-adapter",
            },
            90,
        )
        return {"status": "ok", "market_id": selected.pk}

    with patch("apps.marketdata.views.refresh_quote", side_effect=refresh) as mocked:
        response = client.get(reverse("api-market-quotes"), {"market": market.pk, "refresh": 1})

    assert response.status_code == 200
    quote = response.json()["markets"][0]["quote"]
    assert quote["price"] == "68123.45"
    assert quote["ask"] == "68123.50"
    assert quote["stale"] is False
    mocked.assert_called_once()


@pytest.mark.django_db
def test_fix_loss_refreshes_free_usdt_and_includes_fees(client, manual_workspace):
    owner, account, market = manual_workspace
    BalanceSnapshot.objects.create(
        exchange_account=account,
        asset=market.quote_asset,
        wallet_scope="spot",
        free_balance=Decimal("1000"),
        total_balance=Decimal("1000"),
        captured_at=timezone.now() - timedelta(seconds=31),
    )
    adapter = type(
        "BalanceAdapter",
        (),
        {"fetch_balance": lambda self: [Balance("USDT", Decimal("750"), Decimal("50"))]},
    )()
    client.force_login(owner)
    with patch("apps.tradeplans.fix_loss.get_adapter", return_value=adapter):
        response = client.post(
            reverse("api-fix-loss"),
            {
                "account_id": account.pk,
                "market_id": market.pk,
                "entry": "100",
                "stop": "95",
                "risk_percent": "1",
                "side": "long",
                "leverage": "1",
            },
            content_type="application/json",
        )

    assert response.status_code == 200, response.content
    payload = response.json()
    assert Decimal(payload["available"]) == Decimal("750")
    assert payload["balance_age_seconds"] <= 1
    assert payload["fees_in_risk_budget"] is True
    assert Decimal(payload["estimated_total_risk"]) <= Decimal(payload["risk_budget"])
    assert (
        Decimal(payload["suggested_capital"])
        == Decimal(payload["suggested_capital"]).to_integral_value()
    )
    latest = account.balance_snapshots.order_by("-captured_at", "-pk").first()
    assert latest.free_balance == Decimal("750")
    assert latest.locked_balance == Decimal("50")
