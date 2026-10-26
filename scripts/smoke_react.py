# fmt: off
"""End-to-end smoke for the real React CryptoSniper workspace."""

import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"

import django  # noqa: E402

django.setup()

from apps.exchanges.models import (  # noqa: E402
    Asset,
    BalanceSnapshot,
    Exchange,
    ExchangeMarket,
    LiveSpotOrder,
    UserExchangeAccount,
)
from apps.marketdata.models import HistoricalCandle  # noqa: E402
from apps.signals.models import RawSignal, Signal, SignalSource, SignalTarget  # noqa: E402
from apps.tradeplans.models import TradePlan  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.cache import cache  # noqa: E402
from django.utils import timezone  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


def wait_for(check, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.2)
    raise AssertionError("Timed out waiting for React smoke condition.")


def seed_market(user):
    suffix = secrets.token_hex(4)
    exchange = Exchange.objects.create(
        code=f"react-{suffix}",
        name="React Smoke Exchange",
        adapter_code=f"react-{suffix}",
        spot_supported=True,
        margin_supported=False,
        enabled=True,
    )
    btc, _ = Asset.objects.get_or_create(symbol="BTC")
    usdt, _ = Asset.objects.get_or_create(symbol="USDT")
    now = timezone.now()
    market = ExchangeMarket.objects.create(
        exchange=exchange,
        symbol="BTC/USDT",
        base_asset=btc,
        quote_asset=usdt,
        market_type=ExchangeMarket.MarketType.SPOT,
        min_amount=Decimal("0.0001"),
        amount_step=Decimal("0.0001"),
        price_step=Decimal("0.01"),
        min_notional=Decimal("10"),
        max_leverage=Decimal("1"),
        maker_fee=Decimal("0.0005"),
        taker_fee=Decimal("0.001"),
        synced_at=now,
    )
    account = UserExchangeAccount.objects.create(
        owner=user,
        exchange=exchange,
        label="حساب تست React",
        environment=UserExchangeAccount.Environment.LIVE,
        status=UserExchangeAccount.Status.CONNECTED,
        permissions={
            "can_read": True,
            "can_trade_spot": False,
            "can_trade_margin": False,
            "can_withdraw": False,
            "ip_restricted": True,
        },
        last_verified_at=now,
        last_sync_at=now,
    )
    BalanceSnapshot.objects.create(
        exchange_account=account,
        asset=usdt,
        wallet_scope="spot",
        free_balance=Decimal("1000"),
        locked_balance=Decimal("0"),
        total_balance=Decimal("1000"),
        usd_value=Decimal("1000"),
        captured_at=now,
    )
    for index in range(45):
        opened = now - timedelta(minutes=(45 - index) * 5)
        base = Decimal("64000") + Decimal(index * 20)
        HistoricalCandle.objects.create(
            provider="binance_public",
            symbol="BTC/USDT",
            interval="5m",
            open_time=opened,
            close_time=opened + timedelta(minutes=5),
            open_price=base,
            high_price=base + Decimal("150"),
            low_price=base - Decimal("120"),
            close_price=base + Decimal("60"),
            volume=Decimal("12"),
        )
    cache.set(
        f"marketdata:v1:quote:{market.pk}",
        {
            "market_id": market.pk,
            "exchange": exchange.code,
            "symbol": market.symbol,
            "market_type": market.market_type,
            "price": "65000",
            "bid": "64999",
            "ask": "65001",
            "bids": [["64999", "1"]],
            "asks": [["65001", "1"]],
            "observed_at": now.isoformat(),
            "source": "react_smoke",
        },
        timeout=90,
    )
    return account, market


def seed_signal(user, account, market):
    source = SignalSource.objects.create(
        owner=user,
        name="React Smoke Signal",
        method="manual",
        enabled=True,
    )
    raw = RawSignal.objects.create(
        owner=user,
        source=source,
        original_text="BTC/USDT LONG Entry 65000 TP1 70000 SL 60000",
        original_payload={},
        checksum=secrets.token_hex(32),
    )
    signal = Signal.objects.create(
        owner=user,
        source=source,
        raw_signal=raw,
        exchange_account=account,
        market=market,
        side="long",
        entry_price=Decimal("65000"),
        stop_loss=Decimal("60000"),
        status=Signal.Status.PARSED,
        parsed_payload={"account_id": account.pk, "market_id": market.pk},
    )
    SignalTarget.objects.create(
        signal=signal,
        position=1,
        price=Decimal("70000"),
        share_percent=Decimal("100"),
    )
    return signal


def main():
    username = "react-smoke-" + secrets.token_hex(5)
    password = secrets.token_urlsafe(22)
    user = get_user_model().objects.create_user(
        username=username,
        password=password,
        display_name="کاربر تست React",
    )
    account, market = seed_market(user)
    seed_signal(user, account, market)

    LiveSpotOrder.objects.create(
        owner=user,
        account=account,
        market=market,
        client_order_id="react-smoke-order",
        side="buy",
        order_type="limit",
        amount=Decimal("0.001"),
        price=Decimal("65000"),
        state=LiveSpotOrder.State.OPEN,
    )

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, PYTHONPATH=str(BACKEND))
    artifacts = ROOT / ".runtime" / "screenshots"
    artifacts.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cryptosniper-react-smoke-") as temp:
        log = open(Path(temp) / "web.log", "w+")
        process = subprocess.Popen(
            [
                sys.executable,
                "manage.py",
                "runserver",
                "--noreload",
                f"127.0.0.1:{port}",
            ],
            cwd=BACKEND,
            env=env,
            stdout=log,
            stderr=log,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            wait_for(lambda: httpx.get(base + "/health/ready/", timeout=2).status_code == 200)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))

                page.goto(base + "/auth/login/")
                page.locator('[name="username"]').fill(username)
                page.locator('[name="password"]').fill(password)
                page.get_by_role("button", name="ورود به فضای کار").click()
                page.wait_for_url("**/dashboard/")
                page.locator("#root").wait_for()
                page.locator(".sidebar").wait_for()
                page.locator(".topbar").wait_for()
                page.get_by_text("USDT / USD", exact=False).wait_for()
                page.get_by_text("USDT / تومان", exact=False).wait_for()
                assert page.locator(".s24-shell").count() == 0
                page.screenshot(
                    path=str(artifacts / "react-dashboard-desktop.png"),
                    full_page=True,
                )

                page.get_by_role("button", name="معامله دستی").click()
                page.get_by_role("heading", name="تعریف معامله واقعی").wait_for()
                page.get_by_text("React Smoke Exchange", exact=False).wait_for()
                page.get_by_text("BTC", exact=True).first.wait_for()
                page.locator(".candleChart").wait_for()
                page.get_by_text("Trailing SL", exact=False).wait_for()
                page.get_by_text("شروع Trailing TP", exact=True).wait_for()

                page.get_by_label("Entry").fill("65000")
                page.get_by_label("TP1").fill("70000")
                page.get_by_label("Stop Loss").fill("60000")
                page.get_by_label("حجم ورود").fill("100")
                plans_before = TradePlan.objects.filter(owner=user).count()
                page.get_by_role("button", name="ذخیره برنامه TP/SL").click()
                wait_for(
                    lambda: TradePlan.objects.filter(owner=user).count()
                    == plans_before + 1
                )
                plan = TradePlan.objects.filter(owner=user).latest("pk")
                assert plan.exchange_account_id == account.pk
                assert plan.market_id == market.pk
                assert plan.trailing_sl is True
                assert plan.trailing_trigger == "tp1"
                print("PASS React account -> market -> chart -> real draft")

                page.get_by_role("button", name="صندوق سیگنال").click()
                page.get_by_text("React Smoke Signal", exact=False).first.wait_for()
                page.get_by_text("Signal", exact=False).first.click()
                page.locator(".candleChart").wait_for()
                page.get_by_text("Entry 65", exact=False).wait_for()
                print("PASS React signal inbox + live overlay chart")

                page.get_by_role("button", name="معاملات").click()
                page.get_by_role("heading", name="معاملات یکپارچه").wait_for()
                page.get_by_text("BTC/USDT", exact=True).first.wait_for()
                page.locator(".candleChart").wait_for()
                print("PASS React unified trades + live chart")

                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                )
                page.screenshot(
                    path=str(artifacts / "react-workspace-mobile.png"),
                    full_page=True,
                )
                assert not errors, errors
                browser.close()
        except Exception:
            log.flush()
            log.seek(0)
            print("React web diagnostic:\n" + log.read()[-7000:])
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            log.close()
            get_user_model().objects.filter(pk=user.pk).delete()
            Exchange.objects.filter(pk=account.exchange_id).delete()


if __name__ == "__main__":
    main()
# fmt: on
