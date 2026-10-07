import json

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse


@pytest.fixture(autouse=True)
def clear_rate_limit_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_repeated_login_failures_are_rate_limited(client, django_user_model):
    django_user_model.objects.create_user(username="limited", password="correct-password")
    responses = [
        client.post(reverse("login"), {"username": "limited", "password": "wrong-password"})
        for _ in range(5)
    ]
    assert responses[-1].status_code == 429
    assert responses[-1]["Retry-After"] == "900"
    blocked = client.post(reverse("login"), {"username": "limited", "password": "correct-password"})
    assert blocked.status_code == 429


@pytest.mark.django_db
def test_successful_login_clears_failures_and_suspended_account_is_rejected(
    client, django_user_model
):
    active = django_user_model.objects.create_user(
        username="active-user", password="correct-password"
    )
    for _ in range(4):
        assert (
            client.post(
                reverse("login"), {"username": active.username, "password": "wrong-password"}
            ).status_code
            == 200
        )
    assert (
        client.post(
            reverse("login"), {"username": active.username, "password": "correct-password"}
        ).status_code
        == 302
    )
    client.post(reverse("logout"))
    assert (
        client.post(
            reverse("login"), {"username": active.username, "password": "wrong-password"}
        ).status_code
        == 200
    )
    suspended = django_user_model.objects.create_user(
        username="suspended-user", password="correct-password", account_status="suspended"
    )
    response = client.post(
        reverse("login"), {"username": suspended.username, "password": "correct-password"}
    )
    assert response.status_code == 200
    assert not response.wsgi_request.user.is_authenticated


@pytest.mark.django_db
def test_private_api_is_session_scoped_and_validates_fields(client, django_user_model):
    owner = django_user_model.objects.create_user(
        username="api-owner", email="owner@example.test", password="safe-password"
    )
    django_user_model.objects.create_user(
        username="api-other", email="other@example.test", display_name="Never expose me"
    )
    assert client.get(reverse("api-me")).status_code == 401
    client.force_login(owner)
    response = client.get(reverse("api-me"))
    assert response.status_code == 200
    assert response.json()["profile"]["email"] == owner.email
    assert "Never expose me" not in response.content.decode()
    response = client.patch(
        reverse("api-me"),
        data=json.dumps({"display_name": "API Name", "password": "forbidden"}),
        content_type="application/json",
    )
    assert response.status_code == 400
    owner.refresh_from_db()
    assert owner.display_name == ""


@pytest.mark.django_db
def test_private_api_patch_requires_csrf(django_user_model):
    user = django_user_model.objects.create_user(username="api-csrf", password="safe-password")
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    response = client.patch(
        reverse("api-me"),
        data=json.dumps({"display_name": "Blocked"}),
        content_type="application/json",
    )
    assert response.status_code == 403
