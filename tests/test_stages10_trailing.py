"""Stage10 Paper trailing: boundaries, activation, cancellation and recovery."""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.trading.exits_engine import process_paper_price
from apps.trading.trailing_math import monotonic_stop, percentage_stop
from apps.trading.trailing_rules import configure_trailing
from apps.trading.models import Order, PaperExitFill, Trade, TradeProtection, TradeTarget

from test_stages09_exits import paper_trade


@pytest.mark.django_db
def test_percentage_long_crosses_tp3_then_closes_on_one_percent_reversal(django_user_model):
    user = django_user_model.objects.create_user(username="trail-long")
    trade = paper_trade(user, percentage=True, step=True, two=True)
    one = process_paper_price(trade.pk, price="70000", event_key="trail-a")
    assert one["percentage_active"] is True
    assert one["fill_ids"] == []
    assert Decimal(one["stop"]) == Decimal("69300")
    two = process_paper_price(trade.pk, price="80000", event_key="trail-b")
    assert two["fill_ids"] == [] and two["status"] == "monitored"
    assert Decimal(two["stop"]) == Decimal("79200")
    # TP2 is crossed without selling; Percentage Trailing owns the exit.
    assert not PaperExitFill.objects.filter(trade=trade).exists()
    third = process_paper_price(trade.pk, price="79500", event_key="trail-c")
    assert third["status"] == "monitored"
    assert Decimal(third["stop"]) == Decimal("79200")
    fourth = process_paper_price(trade.pk, price="79100", event_key="trail-d")
    assert fourth["status"] == "closed"
    trade.refresh_from_db()
    assert trade.state == Trade.State.CLOSED
    assert PaperExitFill.objects.filter(trade=trade).count() == 1
    assert PaperExitFill.objects.get(trade=trade).quantity == trade.quantity
    assert not PaperExitFill.objects.filter(trade=trade, reason__startswith="tp").exists()


@pytest.mark.django_db
def test_switch_after_tp_cancel_logical_targets_and_prevent_double_exit(django_user_model):
    user = django_user_model.objects.create_user(username="trail-switch")
    trade = paper_trade(user, percentage=False, step=True, two=True)
    process_paper_price(trade.pk, price="70000", event_key="tp-a")
    first_qty = PaperExitFill.objects.get(trade=trade).quantity
    protection = TradeProtection.objects.get(trade=trade)
    updated = configure_trailing(
        user, trade.pk, version=protection.version,
        step_enabled=True, percentage_enabled=True, distance_percent="1",
        reason="تغییر به فقط trailing"
    )
    assert updated.percentage_enabled
    assert trade.targets.get(position=2).state == TradeTarget.State.CANCELLED
    process_paper_price(trade.pk, price="80000", event_key="tr-high")
    process_paper_price(trade.pk, price="79000", event_key="tr-low")
    fills = list(PaperExitFill.objects.filter(trade=trade))
    assert sum((f.quantity for f in fills), Decimal("0")) == trade.quantity
    assert len(fills) == 2
    assert sum(1 for f in fills if f.reason.startswith("tp")) == 1
    assert Trade.objects.get(pk=trade.pk).state == Trade.State.CLOSED


@pytest.mark.django_db
def test_pending_external_tp_blocks_change_without_assuming_cancel(django_user_model):
    user = django_user_model.objects.create_user(username="trail-pending")
    trade = paper_trade(user, percentage=False, two=True)
    Order.objects.create(
        trade=trade, account=trade.account,
        client_order_id=f"cs-paper-exit-{trade.pk}-tp",
        quantity=Decimal("0.000001"), price=Decimal("70000")
    )
    protection = trade.protection
    with pytest.raises(ValidationError):
        configure_trailing(
            user, trade.pk, version=protection.version,
            step_enabled=True, percentage_enabled=True,
            distance_percent="1", reason="تست لغو نامعلوم"
        )
    protection.refresh_from_db()
    assert not protection.percentage_enabled
    assert trade.targets.get(position=2).state == TradeTarget.State.WAITING


@pytest.mark.django_db
def test_old_duplicate_and_stale_price_tick_are_ignored(django_user_model):
    user = django_user_model.objects.create_user(username="trail-ticks")
    trade = paper_trade(user, percentage=True)
    observed = timezone.now()
    one = process_paper_price(trade.pk, price="72000", observed_at=observed, event_key="same-key")
    assert one["percentage_active"]
    assert process_paper_price(trade.pk, price="72000", observed_at=observed,
                               event_key="same-key")["status"] == "duplicate"
    assert process_paper_price(trade.pk, price="50000",
                               observed_at=observed - timedelta(seconds=1),
                               event_key="old")["status"] == "old_tick"
    assert Trade.objects.get(pk=trade.pk).state == Trade.State.OPEN
    assert TradeProtection.objects.get(trade=trade).high_water == Decimal("72000")


def test_decimal_trailing_math_for_long_and_short():
    assert percentage_stop(side="long", high="80000", distance="1") == Decimal("79200")
    assert percentage_stop(side="short", low="100", distance="1") == Decimal("101")
    assert monotonic_stop("long", Decimal("65000"), Decimal("63000")) == Decimal("65000")
    assert monotonic_stop("short", Decimal("105"), Decimal("110")) == Decimal("105")
    with pytest.raises(ValidationError):
        percentage_stop(side="long", high="100", distance="100")


@pytest.mark.django_db
def test_paper_scenario_owner_boundary_and_mode_guard(client, django_user_model):
    owner = django_user_model.objects.create_user(username="trail-api-owner")
    other = django_user_model.objects.create_user(username="trail-api-stranger")
    trade = paper_trade(owner, percentage=True)
    client.force_login(owner)
    url = f"/paper/{trade.pk}/scenario/"
    assert client.get(url).status_code == 405
    assert client.post(url, {"version":trade.protection.version}).status_code == 302
    rule = TradeProtection.objects.get(trade=trade)
    assert rule.paper_scenario
    result = client.post(f"/paper/{trade.pk}/tick/", {"price":"80000"})
    assert result.status_code == 302
    assert TradeProtection.objects.get(trade=trade).high_water == Decimal("80000")
    client.force_login(other)
    assert client.post(f"/paper/{trade.pk}/tick/", {"price":"10"}).status_code == 404
