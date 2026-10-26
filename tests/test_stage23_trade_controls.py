from decimal import Decimal

import pytest
from apps.tradeplans.calculations import build_preview
from apps.tradeplans.forms import ManualTradeForm
from apps.trading.exits_engine import process_paper_price
from apps.trading.models import TradeProtection
from django.urls import reverse
from test_stages09_exits import paper_trade
from test_tradeplans_stage05 import payload, setup_paper


@pytest.mark.django_db
def test_manual_trigger_integer_controls_and_fresh_entry(client, django_user_model):
    user = django_user_model.objects.create_user(username="stage23-manual")
    account, market = setup_paper(user)
    form = ManualTradeForm(
        user,
        payload(
            account,
            market,
            tp2="75000",
            percentage_trailing="on",
            trailing_trigger="tp2",
            capital="51",
            trailing_distance="2",
        ),
    )
    assert form.is_valid(), form.errors
    preview = build_preview(form.cleaned_data)
    assert preview["trailing_trigger"] == "tp2"
    assert preview["exit_policy"] == "percentage_trailing_only_after_tp2"
    assert preview["capital"] == "51"
    assert preview["trailing_distance_percent"] == "2"
    assert not ManualTradeForm(user, payload(account, market, capital="50.5")).is_valid()
    client.force_login(user)
    page = client.get(reverse("manual-new"))
    assert page.status_code == 200
    assert b'id="root"' in page.content
    assert b"static/react/app.js" in page.content


@pytest.mark.django_db
def test_trailing_sl_moves_to_entry_once_only(django_user_model):
    user = django_user_model.objects.create_user(username="stage23-one-shot-sl")
    trade = paper_trade(user, percentage=False, step=True, three=True)
    process_paper_price(trade.pk, price="70000", event_key="s23-tp1")
    protection = TradeProtection.objects.get(trade=trade)
    assert protection.effective_stop == Decimal("65000")
    process_paper_price(trade.pk, price="75000", event_key="s23-tp2")
    protection.refresh_from_db()
    assert protection.effective_stop == Decimal("65000")
    assert trade.events.filter(event_type="TRAILING_SL_BREAKEVEN").count() == 1


@pytest.mark.django_db
def test_percentage_trigger_can_start_at_tp2(django_user_model):
    user = django_user_model.objects.create_user(username="stage23-trigger-tp2")
    trade = paper_trade(user, percentage=True, two=True, trigger="tp2")
    before = process_paper_price(trade.pk, price="70000", event_key="s23-before")
    assert before["percentage_active"] is False
    active = process_paper_price(trade.pk, price="75000", event_key="s23-trigger")
    assert active["percentage_active"] is True
    protection = TradeProtection.objects.get(trade=trade)
    assert protection.trigger_target == 2
    assert protection.trigger_price == Decimal("75000")
