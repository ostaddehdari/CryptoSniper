from datetime import timedelta
from decimal import Decimal

import pytest
from apps.accounts.models import AuditLog
from apps.accounts.security import STEP_UP_SESSION_KEY
from apps.exchanges.models import (
    Asset,
    BalanceSnapshot,
    Exchange,
    ExchangeMarket,
    LiveSpotOrder,
    UserExchangeAccount,
)
from apps.operations.acceptance import base_product_acceptance
from apps.operations.models import LiveExitAttempt, ManagedSpotPosition
from apps.reports.models import PerformanceAggregate
from django.test import override_settings
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


def _live_position(owner, account):
    btc = Asset.objects.get(symbol="BTC")
    usdt = Asset.objects.get(symbol="USDT")
    market = ExchangeMarket.objects.create(
        exchange=account.exchange,
        symbol="BTC/USDT",
        base_asset=btc,
        quote_asset=usdt,
        market_type="spot",
        max_leverage=1,
    )
    entry = LiveSpotOrder.objects.create(
        owner=owner,
        account=account,
        market=market,
        client_order_id="s33-entry",
        side="buy",
        order_type="limit",
        amount=2,
        price=100,
        filled_amount=2,
        average_price=100,
        fee_amount=Decimal("0.2"),
        fee_asset="USDT",
        fee_quote_value=Decimal("0.2"),
        state="filled",
    )
    position = ManagedSpotPosition.objects.create(
        account=account,
        market=market,
        entry_order=entry,
        snapshot={},
        acquired=2,
        effective_stop=90,
        state="active",
    )
    exit_order = LiveSpotOrder.objects.create(
        owner=owner,
        account=account,
        market=market,
        client_order_id="s33-exit",
        side="sell",
        order_type="limit",
        amount=1,
        price=120,
        filled_amount=1,
        average_price=120,
        fee_amount=Decimal("0.12"),
        fee_asset="USDT",
        fee_quote_value=Decimal("0.12"),
        state="filled",
    )
    LiveExitAttempt.objects.create(
        position=position, order=exit_order, sequence=1, reason="tp1", trigger_price=120
    )
    return exit_order


@pytest.mark.django_db
def test_stage33_live_finance_uses_exact_fills_and_excludes_paper(client, stage33_account):
    owner, account = stage33_account
    _live_position(owner, account)
    PerformanceAggregate.objects.create(
        owner=owner,
        timezone=owner.timezone,
        period_kind="month",
        period_start=timezone.localdate(),
        dimension_kind="total",
        dimension_value="all",
        mode="paper",
        currency="USDT",
        trade_count=1,
        net_realized=999,
        source_fingerprint="paper-must-not-leak",
    )
    client.force_login(owner)
    payload = client.get(reverse("api-live-reports"), {"period": "month"}).json()
    assert payload["mode"] == "live" and payload["source"] == "confirmed_exchange_receipts"
    assert Decimal(payload["total"]["gross_realized"]) == Decimal("20")
    assert Decimal(payload["total"]["fees"]) == Decimal("0.22")
    assert Decimal(payload["total"]["net_realized"]) == Decimal("19.78")
    assert payload["total"]["unknown_count"] == 0


@pytest.mark.django_db
def test_stage33_missing_real_fee_is_unknown_not_zero(client, stage33_account):
    owner, account = stage33_account
    exit_order = _live_position(owner, account)
    exit_order.fee_amount = None
    exit_order.fee_asset = ""
    exit_order.fee_quote_value = None
    exit_order.save(update_fields=("fee_amount", "fee_asset", "fee_quote_value"))
    client.force_login(owner)
    total = client.get(reverse("api-live-reports")).json()["total"]
    assert total["net_realized"] is None
    assert total["unknown_count"] == 1
    assert total["known_net_realized"] == "0"


@override_settings(
    RELEASE_VERSION="0.33.0rc1",
    SOURCE_REVISION="immutable-stage33-test",
    DEPLOYMENT_ENVIRONMENT="production",
    LIVE_TRADING_ENABLED=False,
    LIVE_EXIT_MANAGEMENT_ENABLED=False,
)
def test_stage33_acceptance_is_honest_about_server_and_money_boundaries():
    report = base_product_acceptance()
    assert report["stage"] == "S33"
    assert report["external_validation"]["stage33_target_install"] == "pending_operator_run"
    assert report["live_writes_runtime_enabled"] is False
    assert report["financial_truth"]["missing_exact_fee"] == "unknown_not_zero"
    assert report["product"]["telegram_full_auto"] == "simulator_only"
    assert "secret" not in str(report).lower()
