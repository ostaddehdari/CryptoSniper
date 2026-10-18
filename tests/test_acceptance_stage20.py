"""Stage20 base-product acceptance matrix; Binance writes remain disabled."""

from decimal import Decimal

import pytest
from apps.trading.exits_engine import process_paper_price
from apps.trading.models import PaperExitFill, Position, Trade, TradeTarget
from test_stages09_exits import paper_trade


@pytest.mark.django_db
def test_three_targets_use_10_10_80_and_step_stop_until_close(django_user_model):
    owner = django_user_model.objects.create_user(username="accept-exits20")
    trade = paper_trade(owner, step=True, three=True)
    targets = list(trade.targets.order_by("position"))
    assert [target.share_percent for target in targets] == [
        Decimal("10"),
        Decimal("10"),
        Decimal("80"),
    ]
    first = process_paper_price(trade.pk, price="70000", event_key="accept-tp1")
    assert len(first["fill_ids"]) == 1 and Decimal(first["stop"]) == Decimal("65000")
    second = process_paper_price(trade.pk, price="75000", event_key="accept-tp2")
    assert len(second["fill_ids"]) == 1 and Decimal(second["stop"]) == Decimal("70000")
    final = process_paper_price(trade.pk, price="80000", event_key="accept-tp3")
    trade.refresh_from_db()
    assert final["status"] == "closed" and trade.state == Trade.State.CLOSED
    assert Position.objects.get(trade=trade).quantity == 0
    assert list(trade.targets.values_list("state", flat=True)) == [
        TradeTarget.State.FILLED,
        TradeTarget.State.FILLED,
        TradeTarget.State.FILLED,
    ]


@pytest.mark.django_db
def test_percentage_trailing_crosses_tp3_without_tp_sell_then_closes_once(django_user_model):
    owner = django_user_model.objects.create_user(username="accept-percent20")
    trade = paper_trade(owner, percentage=True, step=True, three=True)
    process_paper_price(trade.pk, price="70000", event_key="accept-percent-on")
    high = process_paper_price(trade.pk, price="80500", event_key="accept-above-tp3")
    assert high["status"] == "monitored" and high["fill_ids"] == []
    assert not PaperExitFill.objects.filter(trade=trade).exists()
    result = process_paper_price(trade.pk, price="79600", event_key="accept-reversal")
    assert result["status"] == "closed"
    fills = PaperExitFill.objects.filter(trade=trade)
    assert fills.count() == 1 and fills.get().reason == "stop"
    assert not fills.filter(reason__startswith="tp").exists()


def test_acceptance_capability_matrix_never_claims_live_or_futures():
    from apps.operations.readiness import engine_readiness

    matrix = engine_readiness()
    assert matrix["adapters"]["simulator_margin_long_short"] == "implemented_and_tested"
    assert matrix["adapters"]["binance_live_write"] == "disabled_not_verified"
    assert matrix["real_order_writes"] is False
