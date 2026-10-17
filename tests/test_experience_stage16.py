"""Stage16 final responsive shell, PWA and accessibility checks."""

import pytest
from apps.signals.models import SignalSource
from django.urls import reverse
from test_stages09_exits import paper_trade


@pytest.mark.django_db
def test_login_and_primary_mobile_navigation(client, django_user_model):
    user = django_user_model.objects.create_user(username="mobile16", password="safe-test-pass")
    login = client.get(reverse("login"))
    assert login.status_code == 200
    assert b'autocomplete="username"' in login.content
    assert b'autocomplete="current-password"' in login.content
    client.force_login(user)
    for name in ("dashboard", "watchlists"):
        response = client.get(reverse(name))
        assert response.status_code == 200
        assert b"mobile-primary-nav" in response.content
        assert b"minimum-scale" not in response.content


@pytest.mark.django_db
def test_manual_and_smart_paste_have_keyboard_safe_preserved_forms(client, django_user_model):
    user = django_user_model.objects.create_user(username="forms16")
    client.force_login(user)
    manual = client.get(reverse("manual-new"))
    smart = client.get(reverse("smart-paste"))
    for response in (manual, smart):
        assert response.status_code == 200
        assert b"data-preserve-form" in response.content
        assert b"form-submit-bar" in response.content
        assert b"form-draft.js" in response.content
    assert b'inputmode="decimal"' in manual.content
    assert b"localStorage" not in smart.content


@pytest.mark.django_db
def test_trade_catalogue_and_detail_keep_vital_mobile_fields(client, django_user_model):
    user = django_user_model.objects.create_user(username="trades16")
    trade = paper_trade(user)
    client.force_login(user)
    catalogue = client.get(reverse("paper-trades"))
    detail = client.get(reverse("paper-trade-detail", args=[trade.pk]))
    assert b"trade-desktop-table" in catalogue.content
    assert b"trade-card-grid" in catalogue.content
    for value in (b"trade-facts", b"trade-timeline", b"Trailing", b"P/L"):
        assert value in detail.content
    assert trade.market.get_market_type_display().encode() in detail.content


@pytest.mark.django_db
def test_settings_routes_are_linked_and_telegram_stays_deferred(client, django_user_model):
    user = django_user_model.objects.create_user(username="settings16")
    telegram = SignalSource.objects.create(
        owner=user, name="کانال آزمایشی", method="telegram", enabled=False
    )
    client.force_login(user)
    page = client.get(reverse("source-settings"))
    assert page.status_code == 200
    for route in (
        "profile",
        "sessions",
        "trading-preferences",
        "source-settings",
        "exchange-center",
        "alerts",
        "reports",
        "audit-events",
    ):
        assert reverse(route).encode() in page.content
    client.post(reverse("source-settings"), {"source_id": telegram.pk, "enabled": "on"})
    telegram.refresh_from_db()
    assert telegram.enabled is False
