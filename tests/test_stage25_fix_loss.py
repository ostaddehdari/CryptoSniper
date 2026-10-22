import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from apps.exchanges.models import (
    Asset,
    BalanceSnapshot,
    Exchange,
    ExchangeMarket,
    UserExchangeAccount,
)
from django.urls import reverse


@pytest.mark.django_db
def test_stage25_fix_loss_matches_free_usdt_risk_formula(client, django_user_model):
    owner = django_user_model.objects.create_user(username="stage25-risk")
    exchange = Exchange.objects.get(code="bitunix")
    usdt, _ = Asset.objects.get_or_create(symbol="USDT")
    btc, _ = Asset.objects.get_or_create(symbol="BTC")
    market, _ = ExchangeMarket.objects.update_or_create(
        exchange=exchange,
        symbol="BTC/USDT",
        market_type="spot",
        defaults={
            "base_asset": btc,
            "quote_asset": usdt,
            "min_amount": Decimal("0.000001"),
            "amount_step": Decimal("0.000001"),
            "price_step": Decimal("0.01"),
            "max_leverage": Decimal("1"),
            "active": True,
        },
    )
    account = UserExchangeAccount.objects.create(
        owner=owner,
        exchange=exchange,
        label="Stage25 Bitunix",
        environment="live",
        status="connected",
    )
    BalanceSnapshot.objects.create(
        exchange_account=account,
        asset=usdt,
        free_balance=Decimal("1000"),
        locked_balance=Decimal("0"),
        total_balance=Decimal("1000"),
        captured_at=datetime.now(UTC),
    )
    client.force_login(owner)

    def calculate(risk):
        response = client.post(
            reverse("api-fix-loss"),
            data=json.dumps(
                {
                    "account_id": account.pk,
                    "market_id": market.pk,
                    "entry": "100",
                    "stop": "95",
                    "risk_percent": str(risk),
                    "leverage": "1",
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 200, response.content
        return response.json()

    one = calculate(1)
    assert Decimal(one["available"]) == Decimal("1000")
    assert Decimal(one["risk_budget"]) == Decimal("10")
    assert Decimal(one["stop_distance_percent"]) == Decimal("5")
    assert Decimal(one["suggested_notional"]) == Decimal("200")

    two = calculate(2)
    assert Decimal(two["risk_budget"]) == Decimal("20")
    assert Decimal(two["suggested_notional"]) == Decimal("400")
