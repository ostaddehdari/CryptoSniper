"""Stage 18 deterministic simulator, shared engine and failure matrix."""

from decimal import Decimal

import pytest
from apps.exchanges.adapters import (
    AdapterError,
    OrderStatus,
    SimulationScenario,
    SimulatorAdapter,
)


def test_seeded_price_path_is_reproducible_and_virtual_time_has_no_sleep():
    scenario = SimulationScenario(seed=1801, volatility_bps=40, virtual_latency_ms=250)
    first, second = SimulatorAdapter(scenario=scenario), SimulatorAdapter(scenario=scenario)
    left, right = [], []
    for _ in range(5):
        left.append(first.fetch_ticker("BTC/USDT").price)
        right.append(second.fetch_ticker("BTC/USDT").price)
        first.advance()
        second.advance()
    assert left == right and len(set(left)) > 1
    assert first.virtual_clock_ms == second.virtual_clock_ms == 1250


def test_partial_fill_market_rules_rate_limit_and_rejection_are_deterministic():
    scenario = SimulationScenario(
        seed=18,
        volatility_bps=0,
        partial_fill_ratio=Decimal("0.5"),
        reject_every=2,
        rate_limit_per_step=1,
    )
    adapter = SimulatorAdapter(scenario=scenario)
    first = adapter.place_order(
        client_order_id="partial-1",
        symbol="BTC/USDT",
        side="buy",
        order_type="market",
        amount="0.002000",
    )
    assert first.status == OrderStatus.PARTIAL
    assert first.filled_amount == Decimal("0.001000")
    with pytest.raises(AdapterError, match="simulated_rejection"):
        adapter.place_order(
            client_order_id="rejected-2",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            amount="0.002000",
        )
    with pytest.raises(AdapterError, match="simulated_rate_limit"):
        adapter.fetch_ticker("BTC/USDT")


@pytest.mark.parametrize("amount", ("0.0000001", "0.0000105"))
def test_simulator_enforces_min_notional_and_lot_step(amount):
    adapter = SimulatorAdapter()
    with pytest.raises(ValueError):
        adapter.place_order(
            client_order_id=f"invalid-{amount}",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            amount=amount,
        )
