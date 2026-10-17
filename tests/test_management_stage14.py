"""Paper operator close: real PostgreSQL concurrency, ownership and durable retries."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from apps.trading.actions import execute_close, request_close
from apps.trading.exits_engine import process_paper_price
from apps.trading.models import PaperExitFill, Trade, TradeAction, TradeEvent, TradeProtection
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from test_stages09_exits import paper_trade


def request(user, trade, key=None, **extra):
    return request_close(
        user,
        trade.pk,
        request_key=key or uuid.uuid4(),
        revision=trade.revision,
        confirmed=True,
        **extra,
    )


@pytest.mark.django_db
def test_request_replay_conflict_and_close_once(django_user_model):
    owner = django_user_model.objects.create_user(username="close14")
    trade = paper_trade(owner)
    key = uuid.uuid4()
    action, created = request(owner, trade, key)
    assert created
    assert request(owner, trade, key)[0].pk == action.pk
    # Different double-click keys coalesce while pending.
    assert request(owner, trade)[0].pk == action.pk
    with pytest.raises(ValidationError):
        request_close(owner, trade.pk, request_key=key, revision=999, confirmed=True)
    result = execute_close(action.pk)
    assert result["state"] == "done"
    assert execute_close(action.pk)["state"] == "done"
    assert Trade.objects.get(pk=trade.pk).state == "closed"
    assert PaperExitFill.objects.filter(trade=trade).count() == 1
    assert PaperExitFill.objects.get(trade=trade).quantity == trade.quantity
    assert TradeAction.objects.get(pk=action.pk).attempts == 1
    assert request(owner, trade, key)[0].state == "done"


@pytest.mark.django_db
def test_close_waits_for_fresh_feed_then_closes_remaining_after_tp(django_user_model):
    owner = django_user_model.objects.create_user(username="retry14")
    trade = paper_trade(owner, two=True)
    process_paper_price(trade.pk, price="70000", event_key="partial-before-close")
    TradeProtection.objects.filter(trade=trade).update(
        paper_scenario=True, last_tick_at=timezone.now() - timedelta(minutes=2)
    )
    trade.refresh_from_db()
    action, _ = request(owner, trade)
    assert execute_close(action.pk)["state"] == "waiting_feed"
    assert Trade.objects.get(pk=trade.pk).state == "open"
    process_paper_price(trade.pk, price="71000", event_key="fresh-close", source="paper_scenario")
    assert execute_close(action.pk)["state"] == "done"
    fills = list(PaperExitFill.objects.filter(trade=trade))
    assert len(fills) == 2
    assert sum((f.quantity for f in fills), Decimal(0)) == trade.quantity


@pytest.mark.django_db
def test_uncertain_partial_and_live_are_blocked(django_user_model):
    owner = django_user_model.objects.create_user(username="guards14")
    trade = paper_trade(owner)
    for state in ["uncertain", "submitting", "partially_filled"]:
        Trade.objects.filter(pk=trade.pk).update(state=state)
        with pytest.raises(ValidationError):
            request(owner, trade)
    Trade.objects.filter(pk=trade.pk).update(state="open")
    trade.account.environment = "live"
    trade.account.save()
    with pytest.raises(ValidationError):
        request(owner, trade)
    assert not TradeAction.objects.exists()


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
@pytest.mark.parametrize("rival", ["stop", "tp", "close"])
def test_concurrent_operator_close_never_oversells(django_user_model, rival):
    owner = django_user_model.objects.create_user(username="race14-" + rival)
    trade = paper_trade(owner)
    action, _ = request(owner, trade)

    def run(which):
        close_old_connections()
        try:
            if which == "close":
                return execute_close(action.pk)
            return process_paper_price(
                trade.pk, price="59000" if which == "stop" else "70000", event_key="race-" + which
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, ["close", rival]))
    assert Trade.objects.get(pk=trade.pk).state == "closed"
    assert (
        sum((f.quantity for f in PaperExitFill.objects.filter(trade=trade)), Decimal(0))
        == trade.quantity
    )
    assert TradeAction.objects.get(pk=action.pk).state == "done"


@pytest.mark.django_db
def test_confirm_csrf_owner_get_and_pending_status(client, django_user_model):
    owner = django_user_model.objects.create_user(username="owner14")
    other = django_user_model.objects.create_user(username="other14")
    trade = paper_trade(owner)
    url = reverse("paper-close", args=[trade.pk])
    client.force_login(owner)
    assert client.get(url).status_code == 405
    values = {"revision": trade.revision, "request_key": str(uuid.uuid4())}
    client.post(url, values)
    assert not TradeAction.objects.exists()
    csrf = Client(enforce_csrf_checks=True)
    csrf.force_login(owner)
    assert csrf.post(url, {**values, "confirmed": "on"}).status_code == 403
    assert client.post(url, {**values, "confirmed": "on"}).status_code == 302
    assert (
        client.get(reverse("paper-status", args=[trade.pk])).json()["actions"][0]["state"]
        == "pending"
    )
    client.force_login(other)
    assert client.post(url, {**values, "confirmed": "on"}).status_code == 404
    assert client.get(reverse("paper-status", args=[trade.pk])).status_code == 404


@pytest.mark.django_db
def test_detail_redacts_event_payload_and_history_filters(client, django_user_model):
    owner = django_user_model.objects.create_user(username="history14")
    trade = paper_trade(owner)
    TradeEvent.objects.create(
        trade=trade,
        event_type="PROVIDER_RECEIPT",
        payload={
            "api_key": "secret-never-render",
            "price": "65000",
            "raw_response": {"token": "secret-never-render"},
        },
    )
    client.force_login(owner)
    detail = client.get(reverse("paper-trade-detail", args=[trade.pk]))
    assert detail.status_code == 200
    assert b"secret-never-render" not in detail.content
    assert client.get("/api/v1/paper/trades/?tab=open").json()["count"] == 1
    assert client.get("/api/v1/paper/trades/?tab=history").json()["count"] == 0
    assert client.get("/api/v1/paper/trades/?coin=ETH").json()["count"] == 0
    assert client.get("/paper/?coin=BTC").status_code == 200
    action, _ = request(owner, trade)
    execute_close(action.pk)
    assert client.get("/api/v1/paper/trades/?tab=history").json()["count"] == 1
    assert client.get("/api/v1/paper/trades/?tab=open").json()["count"] == 0
