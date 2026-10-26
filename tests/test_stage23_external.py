from decimal import Decimal

import pytest
from apps.operations.models import ExternalObservation
from apps.portfolio.external_utils import normalized_external
from test_tradeplans_stage05 import setup_paper


@pytest.mark.django_db
def test_external_normalization_shows_completed_trade_fields(django_user_model):
    user = django_user_model.objects.create_user(username="s23-ext-normalize")
    account, _ = setup_paper(user)
    item = ExternalObservation.objects.create(
        account=account,
        kind="history",
        external_id="BTCUSDT:9",
        payload={
            "symbol": "BTCUSDT",
            "side": "buy",
            "status": "filled",
            "avgPrice": "65000",
            "executedQty": "0.001",
            "time": 1700000000000,
        },
    )
    row = normalized_external(item)
    assert row["symbol"] == "BTC/USDT"
    assert row["side"] == "buy"
    assert row["entry"] == Decimal("65000")
    assert row["amount"] == Decimal("0.001")
    assert row["status_label"] == "تکمیل‌شده"
    assert row["manageable"] is True


@pytest.mark.django_db
def test_paper_external_observation_is_never_manageable_as_live(client, django_user_model):
    user = django_user_model.objects.create_user(username="s23-ext-paper")
    account, _ = setup_paper(user)
    item = ExternalObservation.objects.create(
        account=account,
        kind="fill",
        external_id="BTCUSDT:10",
        payload={"symbol": "BTCUSDT", "isBuyer": True, "price": "65000", "qty": "0.001"},
    )
    client.force_login(user)
    response = client.get(f"/external/{item.pk}/")
    assert response.status_code == 200
    assert b'id="root"' in response.content
    from apps.portfolio.external_management import apply_external_policy
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        apply_external_policy(user, item.pk, {})
