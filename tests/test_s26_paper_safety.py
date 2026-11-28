"""S26 regression coverage for plan, outbox, stale feed and trailing boundaries."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from apps.operations.models import AccountControl, RecoveryIssue
from apps.trading.exits_engine import process_paper_price
from apps.trading.exits_tasks import paper_feed_staleness
from apps.trading.intent import queue_paper_trade
from apps.trading.models import PaperExitFill, TradeEvent, TradeProtection, TradeTarget
from apps.trading.trailing_rules import configure_trailing
from django.core.exceptions import ValidationError
from django.utils import timezone
from test_stages09_exits import paper_trade
from test_trading_stage08 import ready_plan


@pytest.mark.django_db
def test_pending_paper_feed_stale_alert_blocks_new_entry_and_recovers(django_user_model):
    owner = django_user_model.objects.create_user(username="s26-stale-feed")
    trade = paper_trade(owner, percentage=False, two=True)
    protection = TradeProtection.objects.get(trade=trade)
    assert protection.coverage == TradeProtection.Coverage.PENDING
    TradeProtection.objects.filter(pk=protection.pk).update(
        updated_at=timezone.now() - timedelta(minutes=2)
    )
    assert paper_feed_staleness()["stale_count"] == 1
    issue = RecoveryIssue.objects.get(account=trade.account, key=f"paper_feed:{trade.pk}")
    assert issue.code == "paper_feed_stale" and not issue.resolved
    assert AccountControl.objects.get(account=trade.account).paused
    assert TradeEvent.objects.filter(trade=trade, event_type="PAPER_FEED_STALE").count() == 1
    assert paper_feed_staleness()["stale_count"] == 0
    next_plan = ready_plan(owner, trade.account, trade.market)
    with pytest.raises(ValidationError):
        queue_paper_trade(owner, next_plan.pk, request_key=uuid.uuid4())
    fresh = process_paper_price(trade.pk, price="66000", event_key="s26-feed-restored")
    assert fresh["status"] == "monitored"
    issue.refresh_from_db()
    assert issue.resolved
    assert AccountControl.objects.get(account=trade.account).paused  # explicit resume required


@pytest.mark.django_db
def test_percentage_switch_reconciles_partial_exit_and_never_sells_at_tp3(django_user_model):
    owner = django_user_model.objects.create_user(username="s26-percentage")
    trade = paper_trade(owner, percentage=False, step=True, three=True)
    first = process_paper_price(trade.pk, price="70000", event_key="s26-tp1")
    assert first["fill_ids"]
    existing = PaperExitFill.objects.get(trade=trade)
    protection = TradeProtection.objects.get(trade=trade)
    configured = configure_trailing(
        owner,
        trade.pk,
        version=protection.version,
        step_enabled=True,
        percentage_enabled=True,
        distance_percent="1",
        reason="تغییر پس از هدف اول",
    )
    cancellation = TradeEvent.objects.get(trade=trade, event_type="PAPER_TARGETS_CANCELLED")
    assert cancellation.payload["sold_quantity"] == str(existing.quantity)
    assert cancellation.payload["remaining_quantity"] == str(trade.position.quantity)
    assert configured.effective_stop == trade.entry_price
    assert TradeTarget.objects.filter(trade=trade, state="waiting").count() == 0
    high = process_paper_price(trade.pk, price="80000", event_key="s26-tp3-plus")
    assert high["status"] == "monitored" and high["fill_ids"] == []
    assert Decimal(high["stop"]) >= configured.effective_stop
    lower = process_paper_price(trade.pk, price="79500", event_key="s26-lower")
    assert Decimal(lower["stop"]) == Decimal(high["stop"])
    assert PaperExitFill.objects.filter(trade=trade).count() == 1


@pytest.mark.django_db
def test_no_new_percentage_activation_while_feed_stale(django_user_model):
    owner = django_user_model.objects.create_user(username="s26-stale-switch")
    trade = paper_trade(owner, percentage=False, two=True)
    protection = TradeProtection.objects.get(trade=trade)
    protection.coverage = TradeProtection.Coverage.STALE
    protection.save(update_fields=("coverage",))
    with pytest.raises(ValidationError):
        configure_trailing(
            owner,
            trade.pk,
            version=protection.version,
            step_enabled=False,
            percentage_enabled=True,
            distance_percent="1",
            reason="فید هنوز قدیمی است",
        )
    protection.refresh_from_db()
    assert not protection.percentage_enabled
    assert not TradeEvent.objects.filter(trade=trade, event_type="PAPER_TARGETS_CANCELLED").exists()
