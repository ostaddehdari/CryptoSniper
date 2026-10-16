from decimal import Decimal

import pytest
from apps.exchanges.adapters import (
    ExchangeAdapter,
    OrderStatus,
    SimulatorAdapter,
    UnsupportedOperationError,
    get_adapter,
)


def test_simulator_satisfies_contract_and_has_safe_permissions():
    adapter = get_adapter("simulator")
    assert isinstance(adapter, ExchangeAdapter)
    permission = adapter.validate_credentials()
    assert permission.safe_for_trading
    assert permission.can_withdraw is False
    assert {balance.asset for balance in adapter.fetch_balance()} == {"USDT", "BTC", "ETH"}
    assert {market.market_type for market in adapter.fetch_markets()} == {"spot", "margin"}
    assert adapter.fetch_ticker("BTC/USDT").price == Decimal("65000")
    assert adapter.fetch_max_leverage("BTC/USDT") == Decimal("3")


def test_simulator_order_is_idempotent_and_cancellable():
    adapter = SimulatorAdapter()
    intent = {
        "client_order_id": "stable-intent-1",
        "symbol": "BTC/USDT",
        "side": "buy",
        "order_type": "limit",
        "amount": "0.01",
        "price": "60000",
    }
    first = adapter.place_order(**intent)
    second = adapter.place_order(**intent)
    assert first.order_id == second.order_id
    assert first.status == OrderStatus.OPEN
    assert adapter.edit_order(first.order_id, price="61000").price == Decimal("61000")
    assert adapter.cancel_order(first.order_id).status == OrderStatus.CANCELLED
    assert not adapter.fetch_open_orders()


def test_simulator_market_order_and_invalid_market():
    adapter = SimulatorAdapter()
    order = adapter.place_order(
        client_order_id="market-1",
        symbol="ETH/USDT",
        side="sell",
        order_type="market",
        amount="0.2",
    )
    assert order.status == OrderStatus.FILLED
    assert order.filled_amount == Decimal("0.2")
    assert len(adapter.fetch_trade_history()) == 1
    with pytest.raises(UnsupportedOperationError):
        adapter.fetch_ticker("UNKNOWN/USDT")
