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


@pytest.mark.django_db
def test_paper_dispatch_uses_shared_engine_without_real_adapter(monkeypatch, django_user_model):
    import uuid

    from apps.trading.execution import dispatch_paper
    from apps.trading.intent import queue_paper_trade
    from test_trading_stage08 import paper_account, ready_plan

    owner = django_user_model.objects.create_user(username="boundary18")
    account, market = paper_account(owner)
    trade, _ = queue_paper_trade(
        owner, ready_plan(owner, account, market).pk, request_key=uuid.uuid4()
    )

    def external_adapter_forbidden(*args, **kwargs):
        raise AssertionError("Paper execution attempted provider adapter selection")

    monkeypatch.setattr("apps.exchanges.adapters.get_adapter", external_adapter_forbidden)
    assert dispatch_paper(trade.orders.get().outbox.pk)["status"] == "filled"
    trade.refresh_from_db()
    assert trade.mode == "paper" and trade.state == "open"


@pytest.mark.django_db
def test_paper_boundary_rejects_revoked_or_live_account(django_user_model):
    import uuid

    from apps.trading.boundary import require_paper_simulator
    from apps.trading.intent import queue_paper_trade
    from test_trading_stage08 import paper_account, ready_plan

    owner = django_user_model.objects.create_user(username="boundary-reject18")
    account, market = paper_account(owner)
    trade, _ = queue_paper_trade(
        owner, ready_plan(owner, account, market).pk, request_key=uuid.uuid4()
    )
    order = trade.orders.select_related("trade", "account__exchange").get()
    account.credentials_encrypted = ""
    account.save(update_fields=("credentials_encrypted", "updated_at"))
    order.account = account
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        require_paper_simulator(order)
