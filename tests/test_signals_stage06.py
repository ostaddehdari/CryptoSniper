"""Stage 06: idempotent source-scoped ingestion, historical versions and Inbox security."""

import json
from decimal import Decimal

import pytest
from apps.accounts.models import AuditLog
from apps.exchanges.models import Exchange, ExchangeMarket, UserExchangeAccount
from apps.exchanges.security import set_account_credentials
from apps.exchanges.services import sync_exchange_account
from apps.signals.models import RawSignal, RawSignalRevision, SignalRevision
from apps.signals.services import receive_signal, transition, update_parsed
from apps.signals.sources import get_default_source
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse


def account_for(owner):
    exchange = Exchange.objects.get(code="simulator")
    account = UserExchangeAccount(
        owner=owner, exchange=exchange, label=f"Paper-{owner.pk}", environment="paper"
    )
    set_account_credentials(account, {})
    account.save()
    sync_exchange_account(account)
    market = ExchangeMarket.objects.get(exchange=exchange, symbol="BTC/USDT", market_type="spot")
    return account, market


def structure(account, market, *, tp1="70000", tp2=None, side="long"):
    targets = [{"price": Decimal(tp1)}]
    if tp2 is not None:
        targets.append({"price": Decimal(tp2)})
    return {
        "account_id": account.pk,
        "market_id": market.pk,
        "side": side,
        "entry_price": Decimal("65000"),
        "stop_loss": Decimal("60000"),
        "targets": targets,
    }


@pytest.mark.django_db
def test_three_canonical_methods_and_no_external_ingestion(django_user_model):
    owner = django_user_model.objects.create_user(username="sig-owner")
    manual = get_default_source(owner, "manual")
    paste = get_default_source(owner, "smart_paste")
    assert manual.pk != paste.pk
    assert manual.pk == get_default_source(owner, "manual").pk
    assert [k for k, _ in manual.Method.choices] == ["manual", "smart_paste", "telegram"]
    with pytest.raises(ValidationError):
        get_default_source(owner, "telegram")


@pytest.mark.django_db
def test_raw_exact_bytes_idempotency_revision_and_scope(django_user_model):
    owner = django_user_model.objects.create_user(username="sig-raw")
    other = django_user_model.objects.create_user(username="sig-other")
    source = get_default_source(owner, "manual")
    alternate = get_default_source(owner, "smart_paste")
    original = "BTC/USDT \n  Entry: 65000 🚀\n"
    signal, created, revised = receive_signal(
        owner, source, text=original, payload={"sequence": 1}, external_id="msg-7"
    )
    assert created and not revised
    again, created, revised = receive_signal(
        owner, source, text=original, payload={"sequence": 1}, external_id="msg-7"
    )
    assert not created and not revised and again.pk == signal.pk
    assert RawSignal.objects.count() == 1
    changed, created, revised = receive_signal(
        owner, source, text="corrected text", payload={"sequence": 2}, external_id="msg-7"
    )
    assert changed.pk == signal.pk and revised and not created
    signal.refresh_from_db()
    assert signal.raw_signal.original_text == original
    assert signal.raw_signal.revision_number == 2
    assert RawSignalRevision.objects.get(raw_signal=signal.raw_signal, version=2).text == (
        "corrected text"
    )
    assert signal.status == "needs_review"
    separate, created, _ = receive_signal(
        owner, alternate, text=original, payload={"sequence": 1}, external_id="msg-7"
    )
    assert created and separate.raw_signal_id != signal.raw_signal_id
    outsider = get_default_source(other, "manual")
    received, created, _ = receive_signal(
        other, outsider, text=original, payload={"sequence": 1}, external_id="msg-7"
    )
    assert created and received.raw_signal_id != signal.raw_signal_id
    with pytest.raises(ValidationError):
        receive_signal(owner, source, text=" ")


@pytest.mark.django_db
def test_review_transitions_versions_and_immutable_approval(django_user_model):
    owner = django_user_model.objects.create_user(username="sig-review")
    account, market = account_for(owner)
    source = get_default_source(owner)
    signal, _, _ = receive_signal(owner, source, text="BTC/USDT @ 65000")
    with pytest.raises(ValidationError):
        transition(owner, signal.pk, expected_revision=1, action="approve")
    with pytest.raises(ValidationError):
        update_parsed(
            owner,
            signal.pk,
            expected_revision=1,
            reason="valid input",
            data=structure(account, market, tp1="60000"),
        )
    with pytest.raises(ValidationError):
        update_parsed(
            owner,
            signal.pk,
            expected_revision=1,
            reason="valid input",
            data=structure(account, market, side="short"),
        )
    parsed = update_parsed(
        owner,
        signal.pk,
        expected_revision=1,
        data=structure(account, market),
        reason="بازبینی دستی",
    )
    assert parsed.status == "parsed" and parsed.revision == 2
    assert parsed.targets.count() == 1
    with pytest.raises(ValidationError):
        transition(owner, signal.pk, expected_revision=1, action="approve")
    approved = transition(owner, signal.pk, expected_revision=2, action="approve")
    assert approved.status == "approved" and approved.revision == 3
    saved_snapshot = dict(approved.approved_snapshot)
    with pytest.raises(ValidationError):
        transition(owner, signal.pk, expected_revision=3, action="approve")
    with pytest.raises(ValidationError):
        transition(owner, signal.pk, expected_revision=3, action="executed")
    with pytest.raises(ValidationError):
        update_parsed(
            owner,
            signal.pk,
            expected_revision=3,
            data=structure(account, market),
            reason="تغییر غیرمجاز",
        )
    approved.refresh_from_db()
    assert approved.approved_snapshot == saved_snapshot
    assert SignalRevision.objects.filter(signal=signal).count() == 3
    assert AuditLog.objects.filter(owner=owner, event_type="signal.approve").exists()


@pytest.mark.django_db
def test_owner_private_pages_json_history_and_reject(client, django_user_model):
    owner = django_user_model.objects.create_user(username="sig-http")
    stranger = django_user_model.objects.create_user(username="sig-stranger")
    client.force_login(owner)
    text = "  BTC long \n Entry 65000 \n"
    response = client.post(
        reverse("api-inbox-receive"),
        data=json.dumps({"method": "manual", "text": text, "payload": {"raw": True}}),
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    item = response.json()["signal"]
    pk = item["id"]
    assert item["raw"]["original_text"] == text
    assert client.get(reverse("inbox")).status_code == 200
    assert client.get(reverse("inbox-detail", args=[pk])).status_code == 200
    assert client.get(reverse("api-inbox-detail", args=[pk])).json()["signal"]["id"] == pk
    denied = client.post(
        reverse("api-inbox-action", args=[pk]),
        data=json.dumps({"revision": 1, "action": "executed"}),
        content_type="application/json",
    )
    assert denied.status_code == 400
    rejected = client.post(
        reverse("api-inbox-action", args=[pk]),
        data=json.dumps({"revision": 1, "action": "reject", "reason": "ناقص است"}),
        content_type="application/json",
    )
    assert rejected.status_code == 200, rejected.content
    assert rejected.json()["signal"]["status"] == "rejected"
    client.force_login(stranger)
    assert client.get(reverse("inbox-detail", args=[pk])).status_code == 404
    assert client.get(reverse("api-inbox-detail", args=[pk])).status_code == 404
    assert client.get(reverse("api-inbox")).json()["items"] == []
    assert (
        client.post(
            reverse("api-inbox-action", args=[pk]),
            data=json.dumps({"revision": 2, "action": "approve"}),
            content_type="application/json",
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_csrf_required_for_mutations(django_user_model):
    owner = django_user_model.objects.create_user(username="sig-csrf")
    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)
    response = client.post(
        reverse("api-inbox-receive"),
        data=json.dumps({"method": "manual", "text": "BTC"}),
        content_type="application/json",
    )
    assert response.status_code == 403
