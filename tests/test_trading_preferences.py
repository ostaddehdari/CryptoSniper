from decimal import Decimal

import pytest
from apps.accounts.models import TradingPreferences
from django.core.exceptions import ValidationError
from django.urls import reverse


@pytest.mark.django_db
def test_trading_defaults_match_approved_strategy(client, django_user_model):
    user = django_user_model.objects.create_user(username="defaults-user")
    client.force_login(user)
    response = client.get(reverse("api-trading-preferences"))
    assert response.status_code == 200
    data = response.json()["trading_preferences"]
    assert data["tp_distribution"] == ["10.00", "10.00", "80.00"]
    assert data["trailing_sl_enabled"] is True
    assert data["trailing_tp_enabled"] is True
    assert data["trailing_trigger"] == "tp1"
    assert data["trailing_distance_percent"] == "1.000"
    assert data["default_market"] == "spot"


@pytest.mark.django_db
def test_valid_preferences_are_saved_only_for_current_user(client, django_user_model):
    owner = django_user_model.objects.create_user(username="preference-owner")
    other = django_user_model.objects.create_user(username="preference-other")
    other_preferences = TradingPreferences.objects.create(owner=other)
    client.force_login(owner)
    response = client.post(
        reverse("trading-preferences"),
        {
            "default_order_amount": "75.5",
            "default_market": "margin",
            "tp1_percent": "15",
            "tp2_percent": "25",
            "tp3_percent": "60",
            "trailing_sl_enabled": "on",
            "trailing_tp_enabled": "on",
            "trailing_trigger": "tp1",
            "trailing_distance_percent": "1.5",
        },
    )
    assert response.status_code == 302
    own = TradingPreferences.objects.get(owner=owner)
    other_preferences.refresh_from_db()
    assert own.default_order_amount == Decimal("75.50000000")
    assert own.default_market == "margin"
    assert other_preferences.default_order_amount == Decimal("50")
    assert list(TradingPreferences.objects.for_user(owner)) == [own]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("amount", "tp1", "tp2", "tp3", "distance"),
    [
        ("-1", "10", "10", "80", "1"),
        ("50", "10", "10", "70", "1"),
        ("50", "-1", "11", "90", "1"),
        ("50", "10", "10", "80", "0"),
    ],
)
def test_invalid_or_negative_preferences_are_rejected(
    client, django_user_model, amount, tp1, tp2, tp3, distance
):
    user = django_user_model.objects.create_user(username=f"invalid-{amount}-{tp1}-{distance}")
    client.force_login(user)
    response = client.post(
        reverse("trading-preferences"),
        {
            "default_order_amount": amount,
            "default_market": "spot",
            "tp1_percent": tp1,
            "tp2_percent": tp2,
            "tp3_percent": tp3,
            "trailing_trigger": "tp1",
            "trailing_distance_percent": distance,
        },
    )
    assert response.status_code == 200
    preferences = TradingPreferences.objects.get(owner=user)
    assert preferences.default_order_amount == Decimal("50")


@pytest.mark.django_db
def test_model_rejects_invalid_tp_total(django_user_model):
    user = django_user_model.objects.create_user(username="model-validation")
    with pytest.raises(ValidationError):
        TradingPreferences.objects.create(owner=user, tp3_percent=Decimal("70"))
