import json
from datetime import timedelta
from decimal import Decimal

import pytest
from apps.alerts.engine import evaluate
from apps.alerts.forms import AlertForm
from apps.alerts.models import AlertEvent, Notification, NotificationPreference, PriceAlert
from apps.alerts.service import save_alert
from apps.alerts.tasks import evaluate_alerts
from apps.alerts.trade_metrics import trade_metric
from apps.marketdata.feeds import refresh_quote
from apps.trading.execution import dispatch_paper
from apps.trading.exits_engine import process_paper_price
from apps.trading.models import TradeProtection
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from test_operations_stage11 import setup_trade
from test_trading_stage08 import paper_account


def create_alert(user, market, **changes):
    refresh_quote(market)
    data = {
        "title": "هشدار آزمون",
        "market": market.pk,
        "kind": "price",
        "direction": "above",
        "threshold": "66000",
        "hysteresis": ".1",
        "cooldown_seconds": 5,
        "enabled": True,
        "version": 1,
        **changes,
    }
    form = AlertForm(user, data)
    assert form.is_valid(), form.errors
    return save_alert(user, form)


@pytest.mark.django_db
def test_crossing_once_duplicate_and_stale(django_user_model):
    user = django_user_model.objects.create_user(username="alert12")
    _, market = paper_account(user)
    alert = create_alert(user, market)
    now = timezone.now()
    assert (
        evaluate(
            alert.pk, price="67000", observed_at=now - timedelta(minutes=2), source="simulator"
        )
        == "stale"
    )
    assert evaluate(alert.pk, price="67000", observed_at=now, source="simulator") == "fired"
    evaluate(alert.pk, price="67000", observed_at=now, source="simulator")
    assert AlertEvent.objects.count() == Notification.objects.count() == 1
    assert not PriceAlert.objects.get(pk=alert.pk).enabled


@pytest.mark.django_db
def test_repeating_hysteresis_requires_rearm(django_user_model):
    user = django_user_model.objects.create_user(username="repeat12")
    _, market = paper_account(user)
    alert = create_alert(user, market, repeat=True)
    start = timezone.now()
    assert evaluate(alert.pk, price="67000", observed_at=start, source="simulator") == "fired"
    PriceAlert.objects.filter(pk=alert.pk).update(last_fired_at=start - timedelta(seconds=10))
    evaluate(alert.pk, price="67010", observed_at=start + timedelta(seconds=1), source="simulator")
    evaluate(alert.pk, price="65990", observed_at=start + timedelta(seconds=2), source="simulator")
    assert not PriceAlert.objects.get(pk=alert.pk).armed
    evaluate(alert.pk, price="65000", observed_at=start + timedelta(seconds=3), source="simulator")
    assert PriceAlert.objects.get(pk=alert.pk).armed
    assert (
        evaluate(
            alert.pk, price="67000", observed_at=start + timedelta(seconds=4), source="simulator"
        )
        == "fired"
    )
    assert Notification.objects.count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    "kind,threshold,price",
    [("rise", "1", "66000"), ("fall", "1", "64000"), ("price", "64000", "63000")],
)
def test_fixed_reference_both_directions(django_user_model, kind, threshold, price):
    user = django_user_model.objects.create_user(username="percent12")
    _, market = paper_account(user)
    alert = create_alert(
        user,
        market,
        kind=kind,
        threshold=threshold,
        direction="below" if kind == "price" else "above",
    )
    reference = alert.reference_price
    assert (
        evaluate(alert.pk, price=price, observed_at=timezone.now(), source="simulator") == "fired"
    )
    alert.refresh_from_db()
    assert alert.reference_price == reference == Decimal("65000")


@pytest.mark.django_db
def test_trade_profit_includes_fees_and_closed_trade_disables(django_user_model):
    user = django_user_model.objects.create_user(username="profit12")
    trade, box = setup_trade(user)
    dispatch_paper(box.pk)
    trade.refresh_from_db()
    alert = create_alert(user, trade.market, trade=trade.pk, kind="profit", threshold="1")
    metric, basis = trade_metric(alert, Decimal("65000"))
    assert metric < 0 and basis["borrow_interest"] == "0"
    assert Decimal(basis["paid_fees"]) > 0 and Decimal(basis["estimated_remaining_exit_fee"]) > 0
    assert (
        evaluate(alert.pk, price="67000", observed_at=timezone.now(), source="simulator") == "fired"
    )
    another = create_alert(user, trade.market, trade=trade.pk, kind="entry_change", threshold="2")
    process_paper_price(trade.pk, price="59000", event_key="close-alert-test")
    another.refresh_from_db()
    assert not another.enabled and another.status == "trade_closed"


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["near_sl", "near_activation", "near_stop"])
def test_proximity_levels(django_user_model, kind):
    user = django_user_model.objects.create_user(username="proximity12")
    trade, box = setup_trade(user)
    dispatch_paper(box.pk)
    TradeProtection.objects.filter(trade=trade).update(
        percentage_enabled=True,
        percentage_active=kind == "near_stop",
        effective_stop=60000,
        trigger_price=70000,
    )
    alert = create_alert(user, trade.market, trade=trade.pk, kind=kind, threshold="1")
    price = "69500" if kind == "near_activation" else "60300"
    assert (
        evaluate(alert.pk, price=price, observed_at=timezone.now(), source="simulator") == "fired"
    )


@pytest.mark.django_db
def test_price_needs_fresh_basis_and_invalid_owner_market(django_user_model):
    user = django_user_model.objects.create_user(username="basis12")
    _, market = paper_account(user)
    alert = create_alert(user, market)
    other = django_user_model.objects.create_user(username="forbidden12")
    form = AlertForm(
        other,
        {
            "title": "forbidden",
            "market": market.pk,
            "kind": "price",
            "threshold": 1,
            "direction": "above",
            "version": 1,
            "hysteresis": 0.1,
            "cooldown_seconds": 5,
        },
    )
    assert not form.is_valid()
    cache.delete(f"marketdata:v1:quote:{market.pk}")
    values = {
        "title": alert.title,
        "market": market.pk,
        "kind": "price",
        "threshold": "67000",
        "direction": "above",
        "version": 1,
        "hysteresis": ".1",
        "cooldown_seconds": 5,
    }
    form = AlertForm(user, values)
    assert form.is_valid(), form.errors
    with pytest.raises(ValidationError):
        save_alert(user, form)


@pytest.mark.django_db
def test_notifications_private_read_browser_optin(client, django_user_model):
    user = django_user_model.objects.create_user(username="notify12")
    _, market = paper_account(user)
    NotificationPreference.objects.create(owner=user, browser=True)
    alert = create_alert(user, market)
    evaluate(alert.pk, price="67000", observed_at=timezone.now(), source="simulator")
    item = Notification.objects.get()
    client.force_login(user)
    assert client.get(reverse("api-notifications")).json()["unread"] == 1
    assert len(client.post(reverse("notification-browser-claim")).json()["items"]) == 1
    assert client.post(reverse("notification-browser-claim")).json()["items"] == []
    assert client.post(reverse("notification-read", args=[item.pk])).json()["read"]
    assert client.get(reverse("api-notifications")).json()["unread"] == 0
    other = django_user_model.objects.create_user(username="other-notify12")
    client.force_login(other)
    assert client.post(reverse("notification-read", args=[item.pk])).status_code == 404
    assert client.get(reverse("api-alerts")).json()["alerts"] == []


@pytest.mark.django_db
def test_alert_worker_records_without_browser(django_user_model):
    user = django_user_model.objects.create_user(username="worker12")
    _, market = paper_account(user)
    alert = create_alert(user, market)
    payload = cache.get(f"marketdata:v1:quote:{market.pk}")
    payload["price"], payload["observed_at"] = "67000", timezone.now().isoformat()
    cache.set(f"marketdata:v1:quote:{market.pk}", payload, 90)
    assert evaluate_alerts()["fired"] == 1
    assert Notification.objects.filter(owner=user, event__alert=alert).count() == 1


@pytest.mark.django_db
def test_alert_routes_api_csrf_and_version(client, django_user_model):
    user = django_user_model.objects.create_user(username="routes12")
    _, market = paper_account(user)
    alert = create_alert(user, market)
    client.force_login(user)
    for name in ["alerts", "alert-new", "notifications", "operations"]:
        assert client.get(reverse(name)).status_code == 200
    assert client.get(reverse("alert-edit", args=[alert.pk])).status_code == 200
    data = {
        "id": alert.pk,
        "title": "changed",
        "market": market.pk,
        "kind": "price",
        "threshold": "67000",
        "direction": "above",
        "version": 99,
        "hysteresis": ".1",
        "cooldown_seconds": 5,
    }
    response = client.post(
        reverse("api-alerts"), data=json.dumps(data), content_type="application/json"
    )
    assert response.status_code == 400
    from django.test import Client

    protected = Client(enforce_csrf_checks=True)
    protected.force_login(user)
    assert (
        protected.post(
            reverse("api-alerts"), data=json.dumps(data), content_type="application/json"
        ).status_code
        == 403
    )
