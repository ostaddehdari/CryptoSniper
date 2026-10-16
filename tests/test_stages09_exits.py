"""Stage09 exits: tests run against real PostgreSQL/Redis in CI, Paper only."""
import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.exchanges.models import Exchange, ExchangeMarket, UserExchangeAccount
from apps.exchanges.security import set_account_credentials
from apps.exchanges.services import sync_exchange_account
from apps.tradeplans.forms import ManualTradeForm
from apps.tradeplans.service import approve_plan, create_draft
from apps.trading.execution import dispatch_paper
from apps.trading.exits_engine import process_paper_price
from apps.trading.exits_stop import adjust_stop
from apps.trading.intent import queue_paper_trade
from apps.trading.models import (
    CapitalReservation, PaperExitFill, Position, Trade, TradeEvent, TradeTarget
)


def paper_trade(user, *, percentage=False, step=False, capital="50", two=False):
    exchange = Exchange.objects.get(code="simulator")
    account = UserExchangeAccount(owner=user, exchange=exchange,
                                  label=f"Demo-{uuid.uuid4().hex[:8]}", environment="paper")
    set_account_credentials(account, {})
    account.save()
    sync_exchange_account(account)
    market = ExchangeMarket.objects.get(
        exchange=exchange, symbol="BTC/USDT", market_type="spot"
    )
    form = ManualTradeForm(user, {
        "account": str(account.pk), "market": str(market.pk), "source": "manual",
        "side": "long", "entry_price": "65000", "tp1": "70000",
        "tp2": "75000" if two else "", "tp3": "",
        "stop_loss": "60000", "capital": capital, "leverage": "1",
        "trailing_sl": "on" if step else "",
        "percentage_trailing": "on" if percentage else "",
        "trailing_distance": "1", "client_token": str(uuid.uuid4()),
    })
    assert form.is_valid(), form.errors
    plan, _ = create_draft(user, form.cleaned_data)
    approve_plan(user, plan.pk, plan.revision)
    trade, created = queue_paper_trade(user, plan.pk, request_key=uuid.uuid4())
    assert created
    outcome = dispatch_paper(trade.orders.get().outbox.pk)
    assert outcome["status"] == "filled", outcome
    trade.refresh_from_db()
    assert trade.state == Trade.State.OPEN
    return trade


@pytest.mark.django_db
def test_target_allocation_and_dust_remainder(django_user_model):
    user = django_user_model.objects.create_user(username="exit-target")
    trade = paper_trade(user, two=True)
    targets = list(trade.targets.order_by("position"))
    assert len(targets) == 2
    assert [t.share_percent for t in targets] == [Decimal("10"), Decimal("90")]
    assert targets[0].allocated_quantity + targets[1].allocated_quantity == trade.quantity
    assert all(t.allocated_quantity >= 0 for t in targets)
    assert trade.protection.initial_stop == Decimal("60000")


@pytest.mark.django_db
def test_step_tp_then_stop_never_oversells(django_user_model):
    user = django_user_model.objects.create_user(username="exit-steps")
    trade = paper_trade(user, step=True, two=True)
    a = process_paper_price(trade.pk, price="70000", event_key="tp-1")
    assert len(a["fill_ids"]) == 1
    assert trade.protection.effective_stop == Decimal("65000") or (
        trade.protection.__class__.objects.get(trade=trade).effective_stop == Decimal("65000")
    )
    assert process_paper_price(trade.pk, price="70000", event_key="tp-1")["status"] == "duplicate"
    protection = trade.protection.__class__.objects.get(trade=trade)
    assert protection.effective_stop == Decimal("65000")
    process_paper_price(trade.pk, price="64999", event_key="stop-1")
    trade.refresh_from_db()
    assert trade.state == Trade.State.CLOSED
    assert Position.objects.get(trade=trade).quantity == 0
    total = sum((f.quantity for f in PaperExitFill.objects.filter(trade=trade)), Decimal("0"))
    assert total == trade.quantity
    assert PaperExitFill.objects.filter(trade=trade).count() == 2
    assert not CapitalReservation.objects.get(trade=trade).active
    assert process_paper_price(trade.pk, price="60000", event_key="later")["status"] == "inactive"


@pytest.mark.django_db
def test_partial_tp_fill_and_manual_stop_version(django_user_model):
    user = django_user_model.objects.create_user(username="exit-partial")
    trade = paper_trade(user, two=True)
    target = trade.targets.get(position=1)
    partial = target.allocated_quantity / Decimal("2")
    process_paper_price(trade.pk, price="71000", event_key="partial-1",
                        max_fill_quantity=partial)
    target.refresh_from_db()
    assert target.state == TradeTarget.State.PARTIAL
    assert target.filled_quantity == partial
    protection = trade.protection.__class__.objects.get(trade=trade)
    with pytest.raises(ValidationError):
        adjust_stop(user, trade.pk, version=protection.version,
                    mode="manual", price="55000", reason="تضعیف حد ضرر")
    result, changed = adjust_stop(user, trade.pk, version=protection.version,
                                  mode="breakeven", reason="تأمین سرمایه")
    assert changed and result.effective_stop == Decimal("65000")
    with pytest.raises(ValidationError):
        adjust_stop(user, trade.pk, version=protection.version,
                    mode="manual", price="66000", reason="نسخه قدیمی")
    process_paper_price(trade.pk, price="70000", event_key="partial-2")
    assert trade.targets.get(position=1).state == TradeTarget.State.FILLED
    assert TradeEvent.objects.filter(trade=trade, event_type="MANUAL_STOP_MOVED").count() == 1


@pytest.mark.django_db
def test_stop_takes_precedence_and_owner_api_is_private(client, django_user_model):
    owner = django_user_model.objects.create_user(username="exit-owner")
    other = django_user_model.objects.create_user(username="exit-other")
    trade = paper_trade(owner)
    client.force_login(other)
    assert client.post(reverse("paper-stop", args=[trade.pk]), {
        "version":1, "mode":"breakeven", "reason":"تست مالکیت"
    }).status_code == 404
    assert client.post(reverse("api-paper-tick", args=[trade.pk]),
                       data='{"price":"60000"}', content_type="application/json").status_code == 404
    client.force_login(owner)
    assert client.get(reverse("paper-stop", args=[trade.pk])).status_code == 405
    before = trade.protection.effective_stop
    assert before == Decimal("60000")
    result = process_paper_price(trade.pk, price="59000", event_key="loss")
    assert result["status"] == "closed"
    assert PaperExitFill.objects.get(trade=trade).reason == "stop"
