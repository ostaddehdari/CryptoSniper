"""Stage27 form modes and owner-scoped Watchlist handoff."""

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from apps.marketdata.models import Watchlist, WatchlistItem
from apps.tradeplans.forms import ManualTradeForm
from apps.tradeplans.service import approve_plan, create_draft
from apps.trading.intent import queue_paper_trade
from django.core.exceptions import ValidationError
from django.urls import reverse
from test_trading_stage08 import paper_account


def values(account, market, mode="limit"):
    return {
        "account": str(account.pk),
        "market": str(market.pk),
        "source": "manual",
        "entry_mode": mode,
        "side": "long",
        "entry_price": "65000",
        "tp1": "70000",
        "tp2": "72000",
        "tp3": "75000",
        "stop_loss": "60000",
        "capital": "50",
        "leverage": "1",
        "trailing_distance": "1",
        "client_token": str(uuid.uuid4()),
    }


@pytest.mark.django_db
def test_market_preview_requires_fresh_quote_and_never_queues_paper(django_user_model):
    owner = django_user_model.objects.create_user(username="s27-market")
    account, market = paper_account(owner)
    form = ManualTradeForm(owner, values(account, market, mode="market"))
    assert form.is_valid(), form.errors
    with patch("apps.marketdata.feeds.get_quote", return_value=None):
        with pytest.raises(ValidationError, match="قیمت تازه"):
            create_draft(owner, form.cleaned_data)
    fresh = {"price": "65000", "stale": False}
    with patch("apps.marketdata.feeds.get_quote", return_value=fresh):
        plan, created = create_draft(owner, form.cleaned_data)
        assert created and plan.preview["entry_mode"] == "market"
        assert [Decimal(t["distance_percent"]) for t in plan.preview["targets"]] == [
            Decimal("100") / Decimal("13"),
            Decimal("140") / Decimal("13"),
            Decimal("200") / Decimal("13"),
        ]
        approve_plan(owner, plan.pk, plan.revision)
    assert plan.approved_snapshot["entry_mode"] == "market"
    with pytest.raises(ValidationError, match="Paper"):
        queue_paper_trade(owner, plan.pk, request_key=uuid.uuid4())


@pytest.mark.django_db
def test_watchlist_prefills_only_readable_market_and_no_other_owner(client, django_user_model):
    owner = django_user_model.objects.create_user(username="s27-watch")
    stranger = django_user_model.objects.create_user(username="s27-stranger")
    account, market = paper_account(owner)
    own_list = Watchlist.objects.create(owner=owner, name="منتخب")
    WatchlistItem.objects.create(watchlist=own_list, market=market)
    client.force_login(owner)
    watch = client.get(reverse("watchlists")).content.decode()
    assert f"{reverse('manual-new')}?market={market.pk}" in watch
    assert f"{reverse('smart-paste')}?market={market.pk}" in watch
    manual = client.get(reverse("manual-new") + f"?market={market.pk}").content.decode()
    assert f'value="{account.pk}" selected' in manual
    assert f'value="{market.pk}" selected' in manual
    paste = client.get(reverse("smart-paste") + f"?market={market.pk}").content.decode()
    assert "BTC/USDT" in paste
    assert "Entry:" not in paste.split('id="smart-raw"')[1].split("</textarea>")[0]
    client.force_login(stranger)
    manual = client.get(reverse("manual-new") + f"?market={market.pk}").content.decode()
    paste = client.get(reverse("smart-paste") + f"?market={market.pk}").content.decode()
    assert f'value="{market.pk}" selected' not in manual
    assert 'بازار <b dir="ltr">BTC/USDT</b>' not in paste
    assert client.get(reverse("manual-new") + "?market=invalid").status_code == 200
    assert client.get(reverse("smart-paste") + "?market=invalid").status_code == 200
