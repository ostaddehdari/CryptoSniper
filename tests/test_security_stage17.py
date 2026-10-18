"""Stage 17 security regressions; deliberately uses hostile inputs."""

import json

import pytest
from apps.core.security import validate_public_https_url
from apps.exchanges.models import Exchange
from django.core.exceptions import ValidationError
from django.urls import reverse


@pytest.mark.parametrize(
    "url",
    (
        "http://example.com/hook",
        "https://localhost/hook",
        "https://127.0.0.1/hook",
        "https://169.254.169.254/latest/meta-data",
        "https://10.0.0.1/hook",
        "https://user:secret@example.com/hook",
        "file:///etc/passwd",
    ),
)
def test_external_setting_ssrf_urls_are_rejected(url):
    with pytest.raises(ValidationError):
        validate_public_https_url(url)


def test_public_https_url_is_accepted():
    validate_public_https_url("https://api.example.com/v1/callback")


@pytest.mark.django_db
def test_exchange_model_applies_ssrf_validator():
    exchange = Exchange(
        code="hostile",
        name="Hostile",
        adapter_code="hostile",
        website="https://127.0.0.1/private",
    )
    with pytest.raises(ValidationError):
        exchange.save()


@pytest.mark.django_db
def test_private_api_is_owner_scoped_and_hostile_label_is_escaped(client, django_user_model):
    from test_trading_stage08 import paper_account

    owner = django_user_model.objects.create_user(username="secure-owner")
    stranger = django_user_model.objects.create_user(username="secure-stranger")
    account, _ = paper_account(owner)
    account.label = '<script data-canary="xss">alert(1)</script>'
    account.save()

    client.force_login(stranger)
    assert client.get(reverse("api-exchange-account", args=[account.pk])).status_code == 404
    client.force_login(owner)
    page = client.get(reverse("exchange-account-detail", args=[account.pk]))
    assert b"<script data-canary" not in page.content
    assert b"&lt;script data-canary" in page.content


@pytest.mark.django_db
def test_session_api_post_enforces_csrf(django_user_model):
    from django.test import Client

    user = django_user_model.objects.create_user(username="csrf-user")
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(user)
    response = strict.post(
        reverse("api-signal-smart-paste"),
        data=json.dumps({"text": "BTCUSDT Entry 1 TP 2 SL .5"}),
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_rotation_redacts_permissions_and_revocation_stops_execution(client, django_user_model):
    from apps.exchanges.services import permission_payload
    from test_trading_stage08 import paper_account

    owner = django_user_model.objects.create_user(username="credential-owner")
    account, _ = paper_account(owner)
    assert "paper-account" not in str(
        permission_payload(
            __import__("apps.exchanges.adapters", fromlist=["PermissionReport"]).PermissionReport(
                True, True, True, False, True, "paper-account", ("safe",)
            )
        )
    )
    client.force_login(owner)
    assert client.post(reverse("exchange-account-rotate", args=[account.pk])).status_code == 302
    account.refresh_from_db()
    assert account.status == "pending" and not account.trading_enabled
    assert client.post(reverse("exchange-account-revoke", args=[account.pk])).status_code == 302
    account.refresh_from_db()
    assert account.status == "disabled" and not account.credentials_encrypted
    assert account.permissions == {}


@pytest.mark.django_db
def test_credentials_backup_is_encrypted_and_owner_queryset_scoped(django_user_model):
    from apps.exchanges.models import UserExchangeAccount
    from apps.exchanges.security import encrypted_credentials_backup
    from test_trading_stage08 import paper_account

    owner = django_user_model.objects.create_user(username="backup-owner")
    other = django_user_model.objects.create_user(username="backup-other")
    account, _ = paper_account(owner)
    other_account, _ = paper_account(other)
    blob = encrypted_credentials_backup(
        UserExchangeAccount.objects.for_user(owner), "correct horse battery staple"
    )
    assert b"cryptosniper-encrypted-backup-v1" in blob
    assert account.label.encode() not in blob
    assert other_account.label.encode() not in blob


def test_log_redaction_removes_canary_secret(settings):
    import logging

    from apps.core.observability import RedactingJsonFormatter

    formatter = RedactingJsonFormatter()
    line = formatter.format(
        logging.LogRecord("security", logging.ERROR, __file__, 1, "api_key=CANARY-SECRET", (), None)
    )
    assert "CANARY-SECRET" not in line and "[REDACTED]" in line
