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
# Synthetic provider has no adapter/credentials; no exchange request can be sent.
os.environ["LIVE_TRADING_ENABLED"] = "true"
os.environ["LIVE_EXIT_MANAGEMENT_ENABLED"] = "true"

import django  # noqa: E402

django.setup()

from apps.accounts.models import TradingPreferences  # noqa: E402
from apps.exchanges.models import (  # noqa: E402
    Asset,
    BalanceSnapshot,
    Exchange,
    ExchangeMarket,
    LiveSpotOrder,
    UserExchangeAccount,
)
from apps.marketdata.models import ExchangeFavorite, HistoricalCandle  # noqa: E402
from apps.operations.models import (  # noqa: E402
    ExternalObservation,
    LiveExitAttempt,
    ManagedSpotPosition,
)
from apps.signals.models import RawSignal, Signal, SignalSource, SignalTarget  # noqa: E402
from apps.tradeplans.models import TradePlan  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.cache import cache  # noqa: E402
from django.utils import timezone  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


def wait_for(check, seconds=30):
    deadline = time.monotonic() + seconds
    last_error = None
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except (httpx.HTTPError, OSError) as error:
            last_error = error
        time.sleep(0.2)
    raise AssertionError(
        f"Timed out waiting for React smoke condition: {last_error or 'condition false'}"
    )


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
            "can_trade_spot": True,
            "can_trade_margin": False,
            "can_withdraw": False,
            "ip_restricted": True,
        },
        trading_enabled=True,
        last_verified_at=now,
        last_sync_at=now,
    )
    UserExchangeAccount.objects.create(
        owner=user,
        exchange=exchange,
        label="Unreadable second account",
        status=UserExchangeAccount.Status.DISABLED,
        permissions={},
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
    TradingPreferences.objects.create(
        owner=user, default_order_amount=75, trailing_trigger="tp2", trailing_distance_percent=2
    )
    eth, _ = Asset.objects.get_or_create(symbol="ETH")
    ExchangeMarket.objects.create(
        exchange=account.exchange,
        symbol="ETH/USDT",
        base_asset=eth,
        quote_asset=market.quote_asset,
        market_type="spot",
    )

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

            def ready():
                try:
                    return httpx.get(base + "/health/ready/", timeout=2).status_code == 200
                except httpx.TransportError:
                    return False

            wait_for(ready)
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

                page.get_by_role("button", name="معاملات", exact=True).click()
                page.get_by_role("button", name="معامله جدید", exact=True).click()
                page.get_by_role("heading", name="تعریف معامله واقعی").wait_for()
                page.get_by_text("React Smoke Exchange", exact=True).wait_for()
                assert page.get_by_label("Entry", exact=True).input_value() == ""
                page.get_by_label("بازار", exact=True).click()
                page.get_by_role("option", name="BTC", exact=True).click()
                page.locator(".realChart svg").wait_for()
                assert page.get_by_label("Entry", exact=True).input_value() == ""
                assert page.get_by_label("اهرم", exact=True).is_disabled()
                page.wait_for_function(
                    """() => {
                        const el = document.querySelector('[aria-label="شروع Trailing"]');
                        return el?.value === "tp2";
                    }"""
                )
                assert page.get_by_label("حجم ورود", exact=True).input_value() == "75"
                page.get_by_label("Entry", exact=True).fill("65000")
                page.get_by_label("TP1", exact=True).fill("70000")
                page.get_by_label("TP2", exact=True).fill("75000")
                page.get_by_label("TP3", exact=True).fill("80000")
                page.get_by_label("Stop Loss", exact=True).fill("61750")
                page.wait_for_function(
                    "document.querySelector('[data-fixloss-suggestion]')?.textContent.includes('۲۰۰')"
                )
                page.get_by_label("ریسک مجاز", exact=True).fill("2")
                page.wait_for_function(
                    "document.querySelector('[data-fixloss-suggestion]')?.textContent.includes('۴۰۰')"
                )
                assert page.get_by_label("حجم ورود", exact=True).input_value() == "75"
                page.get_by_role("button", name="استفاده از پیشنهاد", exact=True).click()
                assert page.get_by_label("حجم ورود", exact=True).input_value() == "400"
                page.screenshot(path=str(artifacts / "stage30-manual-desktop.png"), full_page=True)
                page.get_by_label("تأیید ارسال سفارش", exact=True).check()
                dropped = {"done": False}

                def lose_first_success(route):
                    response = route.fetch()
                    if response.status == 201 and not dropped["done"]:
                        dropped["done"] = True
                        route.abort()
                    else:
                        route.fulfill(response=response)

                page.route("**/api/v1/manual/submit/", lose_first_success)
                before = LiveSpotOrder.objects.filter(owner=user).count()
                page.get_by_role("button", name="ارسال سفارش", exact=True).click()
                page.locator(".modal input[type=password]").fill(password)
                page.locator(".modal").get_by_role("button", name="تأیید", exact=True).click()
                page.get_by_role("button", name="بررسی مجدد همان درخواست", exact=True).wait_for()
                wait_for(lambda: LiveSpotOrder.objects.filter(owner=user).count() == before + 1)
                page.get_by_role("button", name="بررسی مجدد همان درخواست", exact=True).click()
                page.get_by_role("heading", name="معاملات یکپارچه").wait_for()
                assert LiveSpotOrder.objects.filter(owner=user).count() == before + 1
                page.locator(".realChart text").filter(has_text="SL").first.wait_for()
                page.get_by_text(
                    "برنامهٔ خروج ذخیره شده؛ اجرای خودکار خروج فعال نیست", exact=True
                ).wait_for()
                plan = TradePlan.objects.filter(owner=user).latest("pk")
                assert plan.status == "ready" and plan.trailing_sl and plan.percentage_trailing
                assert plan.trailing_trigger == "tp2" and plan.trailing_distance == 2
                assert LiveSpotOrder.objects.get(source_plan=plan).amount == Decimal(
                    plan.approved_snapshot["quantity"]
                )
                page.unroute("**/api/v1/manual/submit/", lose_first_success)
                print("PASS S30 live UI: empty Entry, automatic Fix Loss 200/400, server quantity")
                print(
                    "PASS S30 step-up resumes same request; lost success response creates one order"
                )

                page.get_by_role("navigation").get_by_role(
                    "button", name="تنظیمات", exact=True
                ).click()
                page.get_by_role("button", name="ارزهای منتخب", exact=True).click()
                page.get_by_role("button", name="＋ ETH", exact=True).click()
                page.get_by_label("حذف ETH", exact=True).wait_for()
                page.get_by_role("button", name="＋ BTC", exact=True).click()
                page.get_by_label("حذف BTC", exact=True).wait_for()
                page.locator(".favoriteRow").filter(has_text="BTC").drag_to(
                    page.locator(".favoriteRow").filter(has_text="ETH")
                )
                wait_for(
                    lambda: (
                        list(
                            ExchangeFavorite.objects.filter(owner=user)
                            .order_by("position")
                            .values_list("symbol", flat=True)
                        )
                        == ["BTC", "ETH"]
                    )
                )
                print("PASS S30 per-exchange favorites drag/drop persists to PostgreSQL")

                page.get_by_role("button", name="صندوق سیگنال").click()
                page.get_by_text("React Smoke Signal", exact=False).first.wait_for()
                page.get_by_text("Signal", exact=False).first.click()
                page.locator(".realChart svg").wait_for()
                page.locator(".realChart text").filter(has_text="Entry").first.wait_for()
                print("PASS React signal inbox + live overlay chart")

                page.get_by_role("button", name="معاملات").click()
                page.get_by_role("heading", name="معاملات یکپارچه").wait_for()
                page.get_by_text("BTC/USDT", exact=True).first.wait_for()
                page.locator(".realChart svg").wait_for()
                print("PASS React unified trades + live chart")
                external = ExternalObservation.objects.create(
                    account=account,
                    kind="fill",
                    external_id="s31-browser-external",
                    payload={"symbol": "BTC/USDT", "side": "buy", "qty": "0.001", "price": "65000"},
                )
                BalanceSnapshot.objects.create(
                    exchange_account=account,
                    asset=market.base_asset,
                    wallet_scope="spot",
                    free_balance=10,
                    total_balance=10,
                    captured_at=timezone.now(),
                )
                page.goto(base + "/app/#/trades")
                page.locator(".clickRow").filter(has_text="خارج از CryptoSniper").first.click()
                page.get_by_label("SL مدیریت", exact=True).fill("61750")
                page.get_by_label("TP1 مدیریت", exact=True).fill("70000")
                page.get_by_label("تأیید واگذاری مدیریت", exact=True).check()
                page.get_by_role("button", name="واگذاری مدیریت خروج", exact=True).click()
                page.get_by_role("button", name="توقف پایش جدید", exact=True).wait_for()
                page.get_by_role("button", name="توقف پایش جدید", exact=True).click()
                page.get_by_role("button", name="ادامه پایش", exact=True).wait_for()
                page.get_by_role("button", name="ادامه پایش", exact=True).click()
                page.get_by_role("button", name="توقف پایش جدید", exact=True).wait_for()
                page.get_by_role("button", name="ویرایش شرایط", exact=True).click()
                page.get_by_label("TP1 مدیریت", exact=True).fill("71000")
                page.get_by_label("تأیید واگذاری مدیریت", exact=True).check()
                page.get_by_role("button", name="ثبت شرایط", exact=True).click()
                wait_for(
                    lambda: ManagedSpotPosition.objects.filter(
                        external_policy__observation=external, snapshot__targets__0__price="71000"
                    ).exists()
                )
                page.wait_for_function("""() => [...document.querySelectorAll('.realChart text')]
                    .some(e => e.textContent.includes('TP1') && e.textContent.includes('۷۱'))""")
                page.locator(".realChart text").filter(has_text="SL").first.wait_for()
                page.screenshot(
                    path=str(artifacts / "stage31-management-desktop.png"), full_page=True
                )
                print("PASS S31 React: explicit adoption, pause/resume, versioned edit")

                for width in (320, 390, 768, 1440):
                    page.set_viewport_size({"width": width, "height": 900})
                    for route in ("dashboard", "manual", "inbox", "trades"):
                        page.goto(base + "/app/#/" + route)
                        page.locator(".sidebar").wait_for()
                        page.wait_for_timeout(250)
                        layout = page.evaluate("""() => ({
                            viewport: innerWidth,
                            width: document.documentElement.scrollWidth
                        })""")
                        if layout["width"] > width:
                            page.screenshot(
                                path=str(artifacts / f"overflow-{route}-{width}.png"),
                                full_page=True,
                            )
                            print(
                                page.evaluate("""() => [...document.querySelectorAll('*')]
                                .filter(e => e.getBoundingClientRect().right > innerWidth + 1)
                                .map(e => ({tag:e.tagName,cls:e.className,
                                    right:e.getBoundingClientRect().right})).slice(-20)""")
                            )
                        assert layout["width"] <= width, (route, layout)
                        if route == "dashboard":
                            page.screenshot(
                                path=str(artifacts / f"react-dashboard-{width}.png"),
                                full_page=True,
                            )
                    print(f"PASS React responsive routes at {width}px")

                page.set_viewport_size({"width": 1440, "height": 1000})
                for label, heading in [
                    ("صرافی‌ها", "صرافی‌ها"),
                    ("تنظیمات", "تنظیمات"),
                    ("وضعیت سیستم", "وضعیت سیستم"),
                ]:
                    page.get_by_role("navigation").get_by_role(
                        "button", name=label, exact=True
                    ).click()
                    page.locator(".topbar h1").filter(has_text=heading).wait_for()
                page.goto(base + "/app/#/missing-page")
                page.locator(".topbar h1").filter(has_text="نمای کلی").wait_for()
                print("PASS React navigation and unknown bookmark recovery")
                page.get_by_role("button", name="خروج", exact=True).click()
                page.wait_for_url("**/auth/login/")
                print("PASS React CSRF-protected POST logout")
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
            LiveExitAttempt.objects.filter(position__account__owner=user).delete()
            ManagedSpotPosition.objects.filter(account__owner=user).delete()
            LiveSpotOrder.objects.filter(owner=user).delete()
            get_user_model().objects.filter(pk=user.pk).delete()
            Exchange.objects.filter(pk=account.exchange_id).delete()


if __name__ == "__main__":
    main()
