"""Stage16 final responsive shell, PWA and accessibility checks."""

import pytest
from django.urls import reverse


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
