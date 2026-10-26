"""Stage15 financial reports stay Decimal, owner-scoped and export-safe."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from apps.portfolio.metrics import result_for, summarize, trade_queryset
from apps.reports.aggregation import rebuild_user_reports
from apps.reports.exports import safe_csv_cell
from apps.reports.models import PerformanceAggregate, ReportRefreshState
from apps.reports.service import report_dataset
from apps.reports.stats import classify_result, report_statistics
from apps.trading.exits_engine import process_paper_price
from apps.trading.models import TradeFinanceEvent
from django.urls import reverse
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


@pytest.mark.django_db
def test_aggregation_is_idempotent_and_uses_user_day_week_month(django_user_model):
    user = django_user_model.objects.create_user(username="aggregate15", timezone="Asia/Tehran")
    trade = paper_trade(user)
    process_paper_price(trade.pk, price="59000", event_key="aggregate-loss")
    closed_at = datetime(2026, 10, 17, 20, 45, tzinfo=ZoneInfo("UTC"))
    trade.exit_fills.update(occurred_at=closed_at)
    first = rebuild_user_reports(user.pk)
    snapshot = list(
        PerformanceAggregate.objects.filter(owner=user)
        .order_by("pk")
        .values_list("pk", "trade_count", "net_realized")
    )
    second = rebuild_user_reports(user.pk)
    assert first["rows"] == second["rows"] == 12  # 3 periods × 4 dimensions
    assert snapshot == list(
        PerformanceAggregate.objects.filter(owner=user)
        .order_by("pk")
        .values_list("pk", "trade_count", "net_realized")
    )
    daily = PerformanceAggregate.objects.get(owner=user, period_kind="day", dimension_kind="total")
    assert str(daily.period_start) == "2026-10-18"
    assert daily.trade_count == 1 and daily.losses == 1


@pytest.mark.django_db
def test_report_ui_api_csv_svg_are_consistent_and_owner_scoped(client, django_user_model):
    owner = django_user_model.objects.create_user(username="exports15")
    other = django_user_model.objects.create_user(username="exports15-other")
    trade = paper_trade(owner)
    process_paper_price(trade.pk, price="59000", event_key="export-loss")
    rebuild_user_reports(owner.pk)
    client.force_login(owner)
    page = client.get("/reports/?period=day&group=total")
    api = client.get("/api/v1/reports/?period=day&group=total")
    csv_response = client.get("/reports/export.csv?period=day&group=total")
    chart = client.get("/reports/chart.svg?period=day&group=total")
    assert (
        page.status_code == api.status_code == csv_response.status_code == chart.status_code == 200
    )
    net = str(api.json()["rows"][0]["net_realized"])
    assert net.encode() in csv_response.content
    assert net.encode() in chart.content
    assert (
        csv_response["Cache-Control"] == "max-age=0, no-cache, no-store, must-revalidate, private"
    )
    client.force_login(other)
    assert client.get("/api/v1/reports/?period=day&group=total").json()["rows"] == []
    assert safe_csv_cell("=IMPORTXML('x')").startswith("'=")
    assert safe_csv_cell("normal") == "normal"


@pytest.mark.django_db
def test_fill_correction_invalidates_cache_and_rebuild_updates_drilldown(client, django_user_model):
    owner = django_user_model.objects.create_user(username="invalidate15")
    trade = paper_trade(owner)
    process_paper_price(trade.pk, price="59000", event_key="invalidate-loss")
    rebuild_user_reports(owner.pk)
    state = ReportRefreshState.objects.get(owner=owner)
    assert state.dirty_at is None and state.built_version == state.source_version
    before = report_dataset(owner, {"period": "day", "group": "exchange"})
    fill = trade.orders.get().fills.get()
    fill.fee += Decimal("1")
    fill.save(update_fields=("fee",))
    state.refresh_from_db()
    assert state.dirty_at is not None and state.source_version > state.built_version
    rebuild_user_reports(owner.pk)
    after = report_dataset(owner, {"period": "day", "group": "exchange"})
    assert after["total"]["net_realized"] == before["total"]["net_realized"] - Decimal("1")
    row = after["rows"][0]
    assert row.drill_query == f"exchange={trade.market.exchange.code}"
    client.force_login(owner)
    page = client.get(f"/paper/?tab=history&{row.drill_query}")
    assert page.status_code == 200 and b'id="root"' in page.content
    payload = client.get(reverse("api-stage24-trades") + "?view=all").json()
    assert any(item["key"] == f"paper:{trade.pk}" for item in payload["trades"])
