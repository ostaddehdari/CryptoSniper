"""Stage 17 security regressions; deliberately uses hostile inputs."""

import json
from datetime import timedelta

import pytest
from apps.core.security import validate_public_https_url
from apps.exchanges.models import Exchange
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone


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
        reverse("api-smart-paste"),
        data=json.dumps({"text": "BTCUSDT Entry 1 TP 2 SL .5"}),
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_rotation_redacts_permissions_and_revocation_stops_execution(client, django_user_model):
    from apps.exchanges.services import permission_payload
    from test_trading_stage08 import paper_account

    owner = django_user_model.objects.create_user(username="credential-owner", password="safe-pass")
    account, _ = paper_account(owner)
    assert "paper-account" not in str(
        permission_payload(
            __import__("apps.exchanges.adapters", fromlist=["PermissionReport"]).PermissionReport(
                True, True, True, False, True, "paper-account", ("safe",)
            )
        )
    )
    client.force_login(owner)
    blocked = client.post(reverse("exchange-account-rotate", args=[account.pk]))
    assert blocked.status_code == 403 and blocked.json()["error"] == "step_up_required"
    assert client.post(reverse("security-step-up"), {"password": "safe-pass"}).status_code == 302
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


@pytest.mark.django_db
def test_two_factor_readiness_is_honest_and_step_up_rotates_session(client, django_user_model):
    from apps.accounts.security import second_factor_status

    user = django_user_model.objects.create_user(username="step-user", password="right-pass")
    client.force_login(user)
    old_key = client.session.session_key
    page = client.get(reverse("security-step-up"))
    assert page.status_code == 200
    assert not second_factor_status()["configured"]
    assert "اجرای Live غیرفعال" in page.content.decode()
    assert client.post(reverse("security-step-up"), {"password": "wrong"}).status_code == 200
    assert client.post(reverse("security-step-up"), {"password": "right-pass"}).status_code == 302
    assert client.session.session_key != old_key


@pytest.mark.django_db
def test_parser_api_rate_limit_and_global_payload_cap(client, django_user_model, settings):
    from django.core.cache import cache

    cache.clear()
    user = django_user_model.objects.create_user(username="limited-user")
    client.force_login(user)
    settings.PARSER_RATE_LIMIT_PER_MINUTE = 2
    endpoint = reverse("api-smart-paste")
    payload = json.dumps({"text": "BTCUSDT Entry 65000 TP 70000 SL 60000"})
    assert client.post(endpoint, payload, content_type="application/json").status_code in {200, 201}
    assert client.post(endpoint, payload, content_type="application/json").status_code in {200, 201}
    limited = client.post(endpoint, payload, content_type="application/json")
    assert limited.status_code == 429 and limited["Retry-After"] == "60"
    oversized = client.post(endpoint, b"x" * 300000, content_type="application/json")
    assert oversized.status_code == 413


@pytest.mark.django_db
def test_retention_removes_only_expired_ephemeral_records(django_user_model):
    from apps.accounts.models import AuditLog, PasswordResetRequest, UserSession
    from apps.accounts.retention import minimize_expired_security_data, retained_audit_events

    user = django_user_model.objects.create_user(username="retention-user")
    reset = PasswordResetRequest.objects.create(
        owner=user, token_digest="a" * 64, expires_at=timezone.now() - timedelta(days=10)
    )
    session = UserSession.objects.create(
        owner=user,
        session_key="r" * 40,
        expires_at=timezone.now() - timedelta(days=40),
        revoked_at=timezone.now() - timedelta(days=31),
    )
    audit = AuditLog.objects.create(owner=user, event_type="security.retained", metadata={})
    result = minimize_expired_security_data()
    assert result["password_resets"] and result["sessions"]
    assert not PasswordResetRequest.objects.filter(pk=reset.pk).exists()
    assert not UserSession.objects.filter(pk=session.pk).exists()
    assert retained_audit_events(user).filter(pk=audit.pk).exists()


def test_security_release_gate_and_runbook_exist():
    from scripts.security_scan import scan

    assert scan() == []
    runbook = open("docs/runbooks/security-incident.md", encoding="utf-8").read()
    assert "یافته باز critical/high مانع Release است" in runbook
    assert "withdrawal خاموش" in runbook
