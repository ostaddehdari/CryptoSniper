"""Stage05 security/Decimal/manual draft lifecycle against real PostgreSQL in CI."""

import json
import uuid
from decimal import Decimal

import pytest
from apps.exchanges.models import Exchange, ExchangeMarket, UserExchangeAccount
from apps.exchanges.security import set_account_credentials
from apps.exchanges.services import sync_exchange_account
from apps.tradeplans.calculations import build_preview
from apps.tradeplans.forms import ManualTradeForm
from apps.tradeplans.models import TradePlan
from apps.tradeplans.service import approve_plan, create_draft
from django.core.exceptions import ValidationError
from django.urls import reverse


def setup_paper(user):
    exchange = Exchange.objects.get(code="simulator")
    account = UserExchangeAccount(
        owner=user, exchange=exchange, label="Manual test", environment="paper"
    )
    set_account_credentials(account, {})
    account.save()
    sync_exchange_account(account)
    return account, ExchangeMarket.objects.get(
        exchange=exchange, symbol="BTC/USDT", market_type="spot"
    )


def payload(account, market, **changes):
    result = {
        "account": str(account.pk),
        "market": str(market.pk),
        "source": "manual",
        "side": "long",
        "entry_price": "65000",
        "tp1": "70000",
        "tp2": "",
        "tp3": "",
        "stop_loss": "60000",
        "capital": "50",
        "leverage": "1",
        "trailing_distance": "1",
        "client_token": str(uuid.uuid4()),
    }
    result.update(changes)
    return result


@pytest.mark.django_db
def test_manual_form_and_spot_long_only(client, django_user_model):
    user = django_user_model.objects.create_user(username="manual-owner")
    account, market = setup_paper(user)
    form = ManualTradeForm(user, payload(account, market))
    assert form.is_valid(), form.errors
    preview = build_preview(form.cleaned_data)
    assert Decimal(preview["quantity"]) > 0
    assert Decimal(preview["estimated_collateral_and_entry_fee"]) <= Decimal("50")
    assert preview["execution_enabled"] is False
    assert preview["targets"][0]["share_percent"] == "100"
    denied = ManualTradeForm(user, payload(account, market, side="short"))
    assert not denied.is_valid()
    assert "side" in denied.errors
    client.force_login(user)
    assert client.get(reverse("manual-new")).status_code == 200
    assert (
        client.get(
            reverse("manual-context") + f"?account={account.pk}&market={market.pk}"
        ).status_code
        == 200
    )


@pytest.mark.django_db
def test_client_idempotency_and_immutable_snapshot(client, django_user_model):
    user = django_user_model.objects.create_user(username="manual-idem")
    account, market = setup_paper(user)
    data = payload(account, market)
    form = ManualTradeForm(user, data)
    assert form.is_valid(), form.errors
    first, created = create_draft(user, form.cleaned_data)
    second, fresh = create_draft(user, form.cleaned_data)
    assert created and not fresh and first.pk == second.pk
    assert TradePlan.objects.filter(owner=user).count() == 1
    bad = ManualTradeForm(user, {**data, "capital": "100"})
    assert bad.is_valid()
    with pytest.raises(ValidationError):
        create_draft(user, bad.cleaned_data)
    ready = approve_plan(user, first.pk, 1)
    assert ready.status == "ready"
    snapshot = dict(ready.approved_snapshot)
    market.taker_fee = Decimal("0.010")
    market.save(update_fields=["taker_fee"])
    ready.refresh_from_db()
    assert ready.approved_snapshot == snapshot
    assert ready.revision == 1
    assert approve_plan(user, ready.pk, 1).approved_snapshot == snapshot
    assert TradePlan.objects.count() == 1


@pytest.mark.django_db
def test_manual_private_pages_and_csrf_and_rest(client, django_user_model):
    owner = django_user_model.objects.create_user(username="manual-api")
    stranger = django_user_model.objects.create_user(username="manual-other")
    account, market = setup_paper(owner)
    values = payload(account, market)
    client.force_login(owner)
    created = client.post(
        reverse("api-manual-create"), data=json.dumps(values), content_type="application/json"
    )
    assert created.status_code == 201, created.content
    plan_id = created.json()["plan"]["id"]
    assert created.json()["plan"]["orders_submitted"] == 0
    repeat = client.post(
        reverse("api-manual-create"), data=json.dumps(values), content_type="application/json"
    )
    assert repeat.status_code == 200 and repeat.json()["created"] is False
    assert client.get(reverse("manual-preview", args=[plan_id])).status_code == 200
    assert client.get(reverse("api-manual-detail", args=[plan_id])).status_code == 200
    client.force_login(stranger)
    assert client.get(reverse("manual-preview", args=[plan_id])).status_code == 404
    assert client.get(reverse("api-manual-detail", args=[plan_id])).status_code == 404
    assert (
        client.post(
            reverse("api-manual-confirm", args=[plan_id]),
            data=json.dumps({"revision": 1}),
            content_type="application/json",
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_errors_cover_steps_targets_available_balance(client, django_user_model):
    user = django_user_model.objects.create_user(username="manual-validation")
    account, market = setup_paper(user)
    wrong_order = ManualTradeForm(user, payload(account, market, tp1="60000"))
    assert wrong_order.is_valid()
    with pytest.raises(ValidationError):
        build_preview(wrong_order.cleaned_data)
    bad_tick = ManualTradeForm(user, payload(account, market, entry_price="65000.001"))
    assert bad_tick.is_valid()
    with pytest.raises(ValidationError):
        build_preview(bad_tick.cleaned_data)
    insufficient = ManualTradeForm(user, payload(account, market, capital="20000"))
    assert insufficient.is_valid()
    with pytest.raises(ValidationError):
        build_preview(insufficient.cleaned_data)
    small = ManualTradeForm(user, payload(account, market, capital="1"))
    assert small.is_valid()
    with pytest.raises(ValidationError):
        build_preview(small.cleaned_data)
    missing_tp = ManualTradeForm(user, payload(account, market, tp2="", tp3="81000"))
    assert not missing_tp.is_valid()
    client.force_login(user)
    response = client.post(reverse("manual-new"), payload(account, market))
    assert response.status_code == 302
    assert TradePlan.objects.filter(owner=user).count() == 1
