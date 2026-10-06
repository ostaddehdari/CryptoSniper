from uuid import uuid4

import pytest
from django.test import Client
from django.urls import reverse


def test_login_is_public_and_workspace_is_private(client):
    response = client.get(reverse("login"))
    assert response.status_code == 200
    assert 'dir="rtl"' in response.content.decode()
    assert client.get(reverse("dashboard")).status_code == 302
    assert client.get(reverse("system")).status_code == 302


@pytest.mark.django_db
def test_login_logout_and_open_redirect_protection(client, django_user_model):
    django_user_model.objects.create_user(username="operator", password="long-test-password")
    response = client.post(
        reverse("login"),
        {
            "username": "operator",
            "password": "long-test-password",
            "next": "https://outside.invalid",
        },
    )
    assert response.status_code == 302
    assert response.url == reverse("dashboard")
    assert client.get(reverse("dashboard")).status_code == 200
    assert client.get(reverse("logout")).status_code == 405
    assert client.post(reverse("logout")).status_code == 302
    assert client.get(reverse("dashboard")).status_code == 302


@pytest.mark.django_db
def test_login_and_probe_require_csrf(django_user_model):
    client = Client(enforce_csrf_checks=True)
    assert (
        client.post(reverse("login"), {"username": "operator", "password": "x"}).status_code == 403
    )
    user = django_user_model.objects.create_user(username="csrf-user", password="long-password")
    client.force_login(user)
    assert client.post(reverse("create-probe"), {"queue": "orders"}).status_code == 403


@pytest.mark.django_db
def test_probe_receipt_is_owned_and_invalid_queue_is_rejected(client, django_user_model):
    from apps.core.models import ServiceProbe

    owner = django_user_model.objects.create_user(username="owner")
    other = django_user_model.objects.create_user(username="other")
    probe = ServiceProbe.objects.create(requested_by=owner, queue="orders", correlation_id=uuid4())
    client.force_login(other)
    assert client.get(reverse("probe-status", args=[probe.pk])).status_code == 404
    assert client.post(reverse("create-probe"), {"queue": "unrecognized"}).status_code == 400
    client.force_login(owner)
    response = client.get(reverse("probe-status", args=[probe.pk]))
    assert response.status_code == 200
    assert response["Cache-Control"].find("no-store") >= 0
