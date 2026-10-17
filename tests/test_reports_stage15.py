"""Stage15 financial reports stay Decimal, owner-scoped and export-safe."""

from decimal import Decimal

import pytest
from apps.portfolio.metrics import result_for, summarize, trade_queryset
from apps.reports.stats import classify_result, report_statistics
from apps.trading.exits_engine import process_paper_price
from apps.trading.models import TradeFinanceEvent
from django.utils import timezone
from test_stages09_exits import paper_trade


@pytest.mark.django_db
def test_fee_asset_conversion_interest_and_repayment_policy(django_user_model):
    user = django_user_model.objects.create_user(username="finance15")
    trade = paper_trade(user)
    entry = trade.orders.get().fills.get()
    entry.fee_asset = trade.market.base_asset
    entry.fee = Decimal("0.00001")
    entry.fee_quote_rate = Decimal("65000")
    entry.save(update_fields=("fee", "fee_asset", "fee_quote_rate"))
    TradeFinanceEvent.objects.create(
        trade=trade,
        asset=trade.market.quote_asset,
        kind="borrow_interest",
        amount="0.12",
        quote_rate=None,
        provider_reference="interest-1",
        occurred_at=timezone.now(),
    )
    TradeFinanceEvent.objects.create(
        trade=trade,
        asset=trade.market.quote_asset,
        kind="repayment",
        amount="20",
        provider_reference="repay-1",
        occurred_at=timezone.now(),
    )
    process_paper_price(trade.pk, price="70000", event_key="report-close")
    process_paper_price(trade.pk, price="59000", event_key="report-final")
    trade = trade_queryset(user).get(pk=trade.pk)
    stats = result_for(trade)
    assert stats["costs_known"] is True
    assert stats["paid_fees"] >= Decimal("0.65")
    assert stats["margin_interest"] == Decimal("0.12")
    assert stats["margin_repaid"] == Decimal("20")
    assert stats["realized"] == stats["gross_realized"] - stats["paid_fees"] - Decimal("0.12")


@pytest.mark.django_db
def test_unknown_fee_conversion_never_invents_net_result(django_user_model):
    user = django_user_model.objects.create_user(username="unknown-cost15")
    trade = paper_trade(user)
    fill = trade.orders.get().fills.get()
    fill.fee_asset = trade.market.base_asset
    fill.fee_quote_rate = None
    fill.save(update_fields=("fee_asset", "fee_quote_rate"))
    data = summarize(user, trade_queryset(user))
    assert data["trades"][0].stats["paid_fees"] is None
    assert data["trades"][0].stats["realized"] is None
    assert data["buckets"][0]["unpriced_open"] == 1


@pytest.mark.django_db
def test_statistics_exclude_open_and_define_breakeven_denominator(django_user_model):
    user = django_user_model.objects.create_user(username="stats15")
    open_trade = paper_trade(user)
    closed_trade = paper_trade(user)
    process_paper_price(closed_trade.pk, price="59000", event_key="stats-loss")
    report = report_statistics(user)
    bucket = report["buckets"][0]
    assert bucket["total_trades"] == 2
    assert bucket["open_trades"] == 1
    assert bucket["closed_trades"] == 1
    assert bucket["losses"] == 1 and bucket["wins"] == 0
    assert bucket["win_rate"] == 0
    assert bucket["best_trade"] == bucket["worst_trade"] < 0
    assert open_trade.pk in {trade.pk for trade in report["trades"]}
    assert classify_result(Decimal("0.00000001")) == "breakeven"
    assert classify_result(Decimal("-0.00000001")) == "breakeven"
    assert classify_result(Decimal("0.00000002")) == "win"
