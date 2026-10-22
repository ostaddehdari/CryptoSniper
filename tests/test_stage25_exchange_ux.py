import json

import pytest
from apps.exchanges.models import Exchange, UserExchangeAccount
from apps.marketdata.models import FavoriteAsset
from django.urls import reverse


@pytest.mark.django_db
def test_stage25_exchange_create_accepts_provider_code(
    client, django_user_model, monkeypatch
):
    owner = django_user_model.objects.create_user(username="stage25-exchange")
    exchange = Exchange.objects.get(code="bitunix")
    queued = []
    monkeypatch.setattr(
        "apps.core.react_views.sync_exchange_account.apply_async",
        lambda args, queue: queued.append((args, queue)),
    )
    client.force_login(owner)
    response = client.post(
        reverse("api-exchange-create"),
        data=json.dumps(
            {
                "exchange": "bitunix",
                "label": "اتصال جدید",
                "api_key": "stage25-key",
                "api_secret": "stage25-secret",
                "no_withdrawal_confirmed": True,
                "ip_restricted_confirmed": True,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    account = UserExchangeAccount.objects.get(owner=owner, exchange=exchange)
    assert account.environment == "live"
    assert account.status == "pending"
    assert account.credentials_encrypted
    assert queued == [([account.pk], "maintenance")]


@pytest.mark.django_db
def test_stage25_favorites_are_scoped_per_exchange(client, django_user_model):
    owner = django_user_model.objects.create_user(username="stage25-favorites")
    bitunix = Exchange.objects.get(code="bitunix")
    lbank = Exchange.objects.get(code="lbank")
    UserExchangeAccount.objects.create(
        owner=owner,
        exchange=bitunix,
        label="Bitunix",
        environment="live",
        status="connected",
    )
    UserExchangeAccount.objects.create(
        owner=owner,
        exchange=lbank,
        label="LBank",
        environment="live",
        status="connected",
    )
    FavoriteAsset.objects.create(owner=owner, exchange=bitunix, symbol="BTC", position=0)
    FavoriteAsset.objects.create(owner=owner, exchange=lbank, symbol="ETH", position=0)
    client.force_login(owner)
    response = client.get(reverse("api-ui-favorites"))
    assert response.status_code == 200
    assert response.json()["by_exchange"] == {"bitunix": ["BTC"], "lbank": ["ETH"]}
