from datetime import timedelta
from decimal import Decimal

import pytest
from apps.accounts.models import AuditLog
from apps.accounts.security import STEP_UP_SESSION_KEY
from apps.exchanges.models import Asset, BalanceSnapshot, Exchange, UserExchangeAccount
from django.urls import reverse
from django.utils import timezone


@pytest.fixture
def stage33_account(django_user_model):
    owner = django_user_model.objects.create_user(username="s33-owner", password="safe-pass")
    exchange = Exchange.objects.create(
        code="s33x", name="Stage 33 Exchange", adapter_code="s33-adapter", enabled=True
    )
    account = UserExchangeAccount.objects.create(
        owner=owner,
        exchange=exchange,
        label="Main",
        environment="live",
        status="connected",
        credentials_encrypted="encrypted-placeholder",
        permissions={"can_read": True, "can_trade_spot": True, "can_withdraw": False},
    )
    usdt = Asset.objects.create(symbol="USDT")
    btc = Asset.objects.create(symbol="BTC")
    captured = timezone.now() - timedelta(minutes=1)
    BalanceSnapshot.objects.create(
        exchange_account=account,
        asset=usdt,
        free_balance=Decimal("125.50"),
        locked_balance=Decimal("4.50"),
        total_balance=Decimal("130"),
        usd_value=Decimal("130"),
        captured_at=captured,
    )
    BalanceSnapshot.objects.create(
        exchange_account=account,
        asset=btc,
        free_balance=Decimal("0.01"),
        total_balance=Decimal("0.01"),
        usd_value=None,
        captured_at=captured,
    )
    return owner, account


@pytest.mark.django_db
def test_stage33_balance_summary_preserves_provider_time_and_unknown_value(client, stage33_account):
    owner, account = stage33_account
    client.force_login(owner)
    response = client.get(reverse("api-ui-bootstrap"))
    assert response.status_code == 200
    payload = response.json()["accounts"][0]
    assert payload["id"] == account.pk
    assert payload["balance_summary"]["free_usdt"] == "125.5000000000000000"
    assert payload["balance_summary"]["known_usd_value"] == "130.00000000"
    assert payload["balance_summary"]["valuation_complete"] is False
    assert payload["balance_summary"]["unknown_assets"] == ["BTC"]
    assert payload["balance_summary"]["captured_at"]
    assert payload["balance_summary"]["stale"] is False


@pytest.mark.django_db
def test_stage33_revoked_account_disappears_from_bootstrap_and_operations(client, stage33_account):
    owner, account = stage33_account
    client.force_login(owner)
    session = client.session
    session[STEP_UP_SESSION_KEY] = timezone.now().isoformat()
    session.save()
    response = client.post(
        reverse("api-react-exchange-revoke", args=[account.pk]),
        {"confirmed": True},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert client.get(reverse("api-ui-bootstrap")).json()["accounts"] == []
    assert client.get(reverse("api-operations-health")).json()["accounts"] == []
    account.refresh_from_db()
    assert account.status == "disabled" and account.credentials_encrypted == ""
    assert AuditLog.objects.filter(
        owner=owner, event_type="exchange_account.credentials_revoked"
    ).exists()
