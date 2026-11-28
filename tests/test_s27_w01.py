"""Stage27 Inbox owner-scoped lifecycle and approval replay."""
import json

import pytest
from apps.trading.models import TradeEvent
from django.urls import reverse
from test_stage23_signal_inbox import make_signal
from test_trading_stage08 import paper_account


@pytest.mark.django_db
def test_inbox_bulk_owner_scope_restore_and_approve_replay(client, django_user_model):
    owner = django_user_model.objects.create_user(username="s27-inbox")
    other = django_user_model.objects.create_user(username="s27-inbox-other")
    account, market = paper_account(owner)
    mine = make_signal(owner, status="parsed", account=account, market=market)
    theirs = make_signal(other)
    client.force_login(owner)
    url = reverse("api-inbox-action", args=[mine.pk])
    body = json.dumps({"action": "approve", "revision": mine.revision})
    assert client.post(url, body, content_type="application/json").status_code == 200
    assert client.post(url, body, content_type="application/json").json()["replayed"] is True
    assert not TradeEvent.objects.exists()
    bulk = reverse("api-inbox-bulk")
    response = client.post(bulk, json.dumps({"action": "trash", "ids": [mine.pk, theirs.pk]}), content_type="application/json")
    assert response.json()["changed"] == 1
    mine.refresh_from_db()
    theirs.refresh_from_db()
    assert mine.trashed_at and not theirs.trashed_at
    assert [row["id"] for row in client.get(reverse("api-inbox") + "?trash=1").json()["items"]] == [mine.pk]
    assert client.post(bulk, json.dumps({"action": "restore", "ids": [mine.pk]}), content_type="application/json").json()["changed"] == 1
    assert client.get(reverse("app-shell")).status_code == 200
