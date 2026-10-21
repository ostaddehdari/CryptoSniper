"""Stage 23 React/live workspace integration checks."""

from decimal import Decimal

import pytest
from apps.exchanges.models import Asset, BalanceSnapshot, Exchange, ExchangeMarket, UserExchangeAccount
from apps.marketdata.models import FavoriteAsset
from apps.signals.models import RawSignal, SignalSource, TelegramAccount, TelegramChannel, TelegramMessage
from django.utils import timezone


def market_fixture(user, *, code="bitunix", adapter=None, symbol="BTC"):
    exchange = Exchange.objects.create(
        code=code,
        name=code.title(),
        adapter_code=adapter or code,
        spot_supported=True,
        enabled=True,
    )
    base, _ = Asset.objects.get_or_create(symbol=symbol)
    quote, _ = Asset.objects.get_or_create(symbol="USDT")
    market = ExchangeMarket.objects.create(
        exchange=exchange,
        symbol=f"{symbol}/USDT",
        base_asset=base,
        quote_asset=quote,
        market_type="spot",
        max_leverage=Decimal("1"),
        min_notional=Decimal("5"),
        active=True,
        synced_at=timezone.now(),
    )
    account = UserExchangeAccount.objects.create(
        owner=user,
        exchange=exchange,
        label=f"{code}-main",
        environment="live",
        status="connected",
        permissions={"can_read": True, "can_trade_spot": True, "can_withdraw": False},
    )
    return exchange, market, account, quote


@pytest.mark.django_db
def test_stage23_shell_dashboard_and_exchange_catalog(client, django_user_model):
    user = django_user_model.objects.create_user(username="stage23-ui")
    market_fixture(user)
    Exchange.objects.create(code="binance", name="Binance", adapter_code="binance", spot_supported=True)
    Exchange.objects.create(code="simulator", name="Simulator", adapter_code="simulator", spot_supported=True)
    client.force_login(user)
    page = client.get("/dashboard/")
    assert page.status_code == 200
    body = page.content.decode()
    assert 'id="cs-shell-root"' in body
    assert 'id="cs-dashboard-root"' in body
    assert "PAPER" not in body
    payload = client.get("/api/v1/exchanges/").json()
    codes = {item["code"] for item in payload["exchanges"]}
    assert "bitunix" in codes
    assert "binance" not in codes and "simulator" not in codes
    assert payload["accounts"][0]["exchange_id"]


@pytest.mark.django_db
def test_manual_markets_account_scope_and_fix_loss(client, django_user_model):
    user = django_user_model.objects.create_user(username="stage23-manual")
    _, market, account, quote = market_fixture(user, code="bitunix", symbol="BTC")
    market_fixture(user, code="lbank", symbol="ETH")
    BalanceSnapshot.objects.create(
        exchange_account=account,
        asset=quote,
        wallet_scope="spot",
        free_balance=Decimal("1000"),
        locked_balance=0,
        total_balance=Decimal("1000"),
        captured_at=timezone.now(),
    )
    client.force_login(user)
    markets = client.get(f"/api/v1/manual/markets/?account={account.pk}").json()["markets"]
    assert [row["id"] for row in markets] == [market.pk]
    response = client.post(
        "/api/v1/manual/fix-loss/",
        data={
            "account_id": account.pk, "market_id": market.pk, "entry": "100",
            "stop_loss": "95", "side": "long", "leverage": "1", "risk_percent": "1",
        },
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    data = response.json()
    assert Decimal(str(data["risk_amount"])) == Decimal("10")
    assert Decimal(str(data["suggested_notional"])) == Decimal("200")
    assert data["calculation_only"] is True


@pytest.mark.django_db
def test_favorites_owner_scope_and_reorder(client, django_user_model):
    owner = django_user_model.objects.create_user(username="stage23-fav")
    other = django_user_model.objects.create_user(username="stage23-other")
    exchange, _, _, _ = market_fixture(owner, code="bitunix", symbol="BTC")
    eth, _ = Asset.objects.get_or_create(symbol="ETH")
    usdt = Asset.objects.get(symbol="USDT")
    ExchangeMarket.objects.create(
        exchange=exchange, symbol="ETH/USDT", base_asset=eth, quote_asset=usdt,
        market_type="spot", active=True, synced_at=timezone.now(),
    )
    FavoriteAsset.objects.create(owner=other, symbol="BTC", position=0)
    client.force_login(owner)
    for symbol in ("BTC", "ETH"):
        response = client.post(
            "/api/v1/favorites/", data={"action": "add", "symbol": symbol},
            content_type="application/json",
        )
        assert response.status_code in (200, 201)
    rows = client.post(
        "/api/v1/favorites/",
        data={"action": "reorder", "symbols": ["ETH", "BTC"]},
        content_type="application/json",
    ).json()["items"]
    assert [row["symbol"] for row in rows] == ["ETH", "BTC"]
    assert FavoriteAsset.objects.filter(owner=other).count() == 1


@pytest.mark.django_db
def test_telegram_message_search_owner_scope(client, django_user_model):
    owner = django_user_model.objects.create_user(username="stage23-tg")
    other = django_user_model.objects.create_user(username="stage23-tg-other")

    def row(user, suffix, text, checksum):
        source = SignalSource.objects.create(owner=user, name=f"tg-{suffix}", method="telegram")
        raw = RawSignal.objects.create(
            owner=user, source=source, original_text=text, checksum=checksum * 64
        )
        account = TelegramAccount.objects.create(owner=user, status="connected")
        channel = TelegramChannel.objects.create(
            owner=user, account=account, source=source, peer_id=1000 + user.pk, title=f"Channel {suffix}"
        )
        TelegramMessage.objects.create(
            owner=user, channel=channel, message_id=1, text_checksum=("c" if user == owner else "d") * 64,
            raw_signal=raw, message_kind="signal", occurred_at=timezone.now(),
        )
        return channel

    channel = row(owner, "mine", "#BTC LONG Entry 100", "a")
    row(other, "private", "#ETH LONG secret", "b")
    client.force_login(owner)
    result = client.get(f"/api/v1/telegram/messages/?q=%23BTC&channel={channel.pk}").json()
    assert len(result["items"]) == 1
    assert result["items"][0]["text"] == "#BTC LONG Entry 100"
    assert "secret" not in str(result)


@pytest.mark.django_db
def test_archived_exchange_account_hidden(django_user_model):
    user = django_user_model.objects.create_user(username="stage23-archive")
    _, _, account, _ = market_fixture(user)
    account.archived_at = timezone.now()
    account.save(update_fields=("archived_at", "updated_at"))
    assert not UserExchangeAccount.objects.for_user(user).filter(pk=account.pk).exists()
