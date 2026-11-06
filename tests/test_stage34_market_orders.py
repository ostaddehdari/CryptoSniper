from decimal import Decimal
from uuid import uuid4

import pytest
from apps.exchanges.adapters import Order, OrderStatus, PermissionReport
from apps.exchanges.lbank import LbankAdapter
from apps.exchanges.live_orders import (
    execute_live_spot_order,
    queue_live_spot_order,
    supports_order_type,
)
from apps.exchanges.models import (
    Asset,
    BalanceSnapshot,
    Exchange,
    ExchangeMarket,
    UserExchangeAccount,
)
from apps.tradeplans.forms import ManualTradeForm
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils import timezone


@pytest.fixture
def live_market_workspace(django_user_model):
    owner = django_user_model.objects.create_user(username="s34-market-owner")
    exchange = Exchange.objects.create(
        code="s34-lbank",
        name="S34 LBank",
        adapter_code="lbank",
        enabled=True,
        spot_supported=True,
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
        taker_fee=Decimal("0.001"),
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


def test_stage34_provider_capabilities_fail_closed():
    assert supports_order_type("lbank", "market") is True
    assert supports_order_type("bitunix", "market") is True
    assert supports_order_type("weex", "market") is True
    assert supports_order_type("ourbit", "market") is True
    assert supports_order_type("nobitex", "market") is False
    assert supports_order_type("unknown", "market") is False
    assert supports_order_type("nobitex", "limit") is True


def test_stage34_lbank_market_receipt_normalizes_side_and_type():
    receipt = LbankAdapter()._lbank_order(
        {
            "order_id": "market-1",
            "symbol": "btc_usdt",
            "type": "buy_market",
            "amount": "0.002",
            "deal_amount": "0",
            "status": "0",
        }
    )
    assert receipt.side == "buy"
    assert receipt.order_type == "market"
    assert receipt.price is None


@pytest.mark.django_db
@override_settings(LIVE_TRADING_ENABLED=True)
def test_stage34_market_queue_is_durable_and_idempotent(live_market_workspace):
    owner, account, market = live_market_workspace
    key = uuid4()
    intent = {
        "request_key": key,
        "market": market,
        "side": "buy",
        "order_type": "market",
        "amount": Decimal("0.002"),
        "price": None,
        "reference_price": Decimal("65000"),
    }
    first, created = queue_live_spot_order(owner, account, intent)
    second, repeated = queue_live_spot_order(owner, account, intent)
    assert created is True and repeated is False
    assert first.pk == second.pk
    assert first.order_type == "market"
    assert first.price is None
    assert first.reference_price == Decimal("65000")
    with pytest.raises(ValidationError):
        queue_live_spot_order(owner, account, {**intent, "reference_price": Decimal("66000")})


@pytest.mark.django_db
def test_stage34_nobitex_market_is_rejected_before_plan_creation(
    live_market_workspace,
):
    owner, account, market = live_market_workspace
    account.exchange.adapter_code = "nobitex"
    account.exchange.save(update_fields=("adapter_code",))
    form = ManualTradeForm(
        owner,
        {
            "account": account.pk,
            "market": market.pk,
            "source": "manual",
            "side": "long",
            "order_type": "market",
            "entry_price": "65000",
            "stop_loss": "62000",
            "tp1": "68000",
            "capital": "100",
            "leverage": "1",
            "trailing_distance": "1",
            "client_token": uuid4(),
        },
    )
    assert form.is_valid() is False
    assert "order_type" in form.errors


@pytest.mark.django_db
@override_settings(LIVE_TRADING_ENABLED=True)
def test_stage34_market_execution_refreshes_book_and_sends_no_limit_price(
    live_market_workspace, monkeypatch
):
    owner, account, market = live_market_workspace
    order, _ = queue_live_spot_order(
        owner,
        account,
        {
            "request_key": uuid4(),
            "market": market,
            "side": "buy",
            "order_type": "market",
            "amount": Decimal("0.002"),
            "price": None,
            "reference_price": Decimal("65000"),
        },
    )
    placed = {}

    class Adapter:
        def validate_credentials(self):
            return PermissionReport(True, True, False, False, True)

        def fetch_orderbook(self, symbol):
            return {
                "symbol": symbol,
                "bids": [(Decimal("65009"), Decimal("1"))],
                "asks": [(Decimal("65010"), Decimal("1"))],
                "observed_at": timezone.now(),
            }

        def place_order(self, **intent):
            placed.update(intent)
            return Order(
                order_id="provider-market-1",
                client_order_id=intent["client_order_id"],
                symbol=intent["symbol"],
                side=intent["side"],
                order_type="market",
                amount=intent["amount"],
                price=None,
                filled_amount=intent["amount"],
                average_price=Decimal("65010"),
                status=OrderStatus.FILLED,
                created_at=timezone.now(),
            )

    monkeypatch.setattr("apps.exchanges.live_orders.get_adapter", lambda *a, **k: Adapter())
    monkeypatch.setattr("apps.exchanges.live_orders.get_account_credentials", lambda a: {})
    result = execute_live_spot_order(order.pk)
    order.refresh_from_db()
    assert result["status"] == "filled"
    assert placed["order_type"] == "market"
    assert placed["price"] is None
    assert order.reference_price == Decimal("65000")
    assert order.filled_amount == Decimal("0.002")
