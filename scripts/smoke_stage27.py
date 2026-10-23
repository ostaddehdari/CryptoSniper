"""Stage27 browser smoke for the reported production workflow regressions.

No exchange credential is created and no real order is submitted.
"""

import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from decimal import Decimal
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.utils import timezone  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from apps.exchanges.models import (  # noqa: E402
    Asset,
    BalanceSnapshot,
    Exchange,
    ExchangeMarket,
    UserExchangeAccount,
)
from apps.operations.models import ExternalObservation  # noqa: E402
from apps.signals.models import (  # noqa: E402
    RawSignal,
    Signal,
    SignalSource,
    SignalTarget,
)


def wait_for(check, seconds=35):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return
        time.sleep(0.25)
    raise AssertionError("Timed out waiting for Stage27 smoke readiness.")


def seed(owner):
    exchange = Exchange.objects.get(code="bitunix")
    usdt, _ = Asset.objects.get_or_create(symbol="USDT")
    btc, _ = Asset.objects.get_or_create(symbol="BTC")
    eth, _ = Asset.objects.get_or_create(symbol="ETH")
    account = UserExchangeAccount.objects.create(
        owner=owner,
        exchange=exchange,
        label="Stage27 Bitunix",
        environment="live",
        status="connected",
        trading_enabled=True,
        permissions={
            "can_read": True,
            "can_trade_spot": True,
            "can_trade_margin": False,
            "can_withdraw": False,
        },
    )
    markets = {}
    for base, asset in (
        ("BTC", btc),
        ("ETH", eth),
    ):
        markets[base] = ExchangeMarket.objects.create(
            exchange=exchange,
            symbol=f"{base}/USDT",
            base_asset=asset,
            quote_asset=usdt,
            market_type="spot",
            min_amount=Decimal("0.001"),
            amount_step=Decimal("0.001"),
            price_step=Decimal("1"),
            max_leverage=Decimal("1"),
            taker_fee=Decimal("0.001"),
            active=True,
            synced_at=timezone.now(),
        )
    BalanceSnapshot.objects.create(
        exchange_account=account,
        asset=usdt,
        free_balance=Decimal("1000"),
        locked_balance=Decimal("0"),
        total_balance=Decimal("1000"),
        captured_at=timezone.now(),
    )
    ExternalObservation.objects.create(
        account=account,
        kind="fill",
        external_id="BTCUSDT:stage27",
        payload={
            "symbol": "BTCUSDT",
            "side": "buy",
            "executedQty": "0.010",
            "averagePrice": "80000",
            "status": "filled",
        },
    )
    source = SignalSource.objects.create(
        owner=owner,
        name="Stage27 smart",
        method=SignalSource.Method.SMART_PASTE,
    )
    raw = RawSignal.objects.create(
        owner=owner,
        source=source,
        original_text="BTCUSDT LONG ENTRY 80000 TP 82000 84000 86000 SL 78000",
        original_payload={},
        checksum="stage27-browser-signal",
    )
    signal = Signal.objects.create(
        owner=owner,
        source=source,
        raw_signal=raw,
        exchange_account=account,
        market=markets["BTC"],
        side="long",
        entry_price=Decimal("80000"),
        stop_loss=Decimal("78000"),
        technical_confidence=100,
        parser_version="rules-v2",
        parsed_payload={
            "parser_version": "rules-v2",
            "pair": "BTC/USDT",
            "trailing_defaults": {
                "trailing_sl": True,
                "percentage_trailing": True,
                "percentage_trigger": "tp1",
                "percentage_distance": "1",
            },
        },
        status=Signal.Status.PARSED,
    )
    SignalTarget.objects.bulk_create(
        [
            SignalTarget(
                signal=signal,
                position=i,
                price=price,
                share_percent=share,
            )
            for i, price, share in (
                (1, Decimal("82000"), Decimal("10")),
                (2, Decimal("84000"), Decimal("10")),
                (3, Decimal("86000"), Decimal("80")),
            )
        ]
    )
    return account, markets, signal


def main():
    call_command("migrate", interactive=False, verbosity=0)
    call_command("collectstatic", interactive=False, verbosity=0)

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    username = "stage27-" + secrets.token_hex(5)
    password = secrets.token_urlsafe(22)
    owner = get_user_model().objects.create_user(
        username=username,
        password=password,
        display_name="کاربر آزمون Stage27",
    )
    seed(owner)

    env = dict(os.environ, PYTHONPATH=str(BACKEND))
    artifacts = ROOT / ".runtime" / "screenshots"
    artifacts.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cryptosniper-stage27-") as work:
        log_path = Path(work) / "web.log"
        with log_path.open("w+") as log:
            web = subprocess.Popen(
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
                        return httpx.get(
                            base + "/health/ready/",
                            timeout=3,
                        ).status_code == 200
                    except httpx.TransportError:
                        return False

                wait_for(ready)
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch()
                    context = browser.new_context(
                        viewport={"width": 1440, "height": 1000}
                    )
                    page = context.new_page()
                    errors = []
                    inbox_responses = []
                    page.on(
                        "pageerror",
                        lambda error: errors.append(str(error)),
                    )
                    page.on(
                        "response",
                        lambda response: (
                            inbox_responses.append(
                                (response.status, response.url)
                            )
                            if "/api/v1/inbox/" in response.url
                            else None
                        ),
                    )

                    page.goto(base + "/auth/login/")
                    page.locator('[name="username"]').fill(username)
                    page.locator('[name="password"]').fill(password)
                    page.get_by_role(
                        "button",
                        name="ورود به فضای کار",
                    ).click()
                    page.wait_for_url("**/app/")

                    # Work 1: manual market picker actually selects, Entry stays blank.
                    page.get_by_role(
                        "button",
                        name="معامله جدید",
                    ).first.click()
                    page.get_by_role(
                        "button",
                        name="انتخاب بازار",
                    ).wait_for()
                    entry_field = page.locator(
                        ".field",
                        has_text="Entry",
                    ).locator("input")
                    assert entry_field.input_value() == ""
                    page.get_by_role(
                        "button",
                        name="انتخاب بازار",
                    ).click()
                    page.get_by_placeholder(
                        "جست‌وجوی BTC، ETH…",
                    ).fill("ETH")
                    page.locator(".marketOptions button", has_text="ETH / USDT").click()
                    page.locator(
                        ".marketSelectButton",
                        has_text="ETH / USDT",
                    ).wait_for()
                    assert entry_field.input_value() == ""

                    # Work 2: settings semantics.
                    page.locator("aside.sidebar").get_by_text(
                        "تنظیمات",
                        exact=True,
                    ).click()
                    page.get_by_role(
                        "button",
                        name="پیش‌فرض معامله",
                        exact=True,
                    ).click()
                    page.get_by_text("Trailing", exact=True).wait_for()
                    page.get_by_text("Trailing SL", exact=True).wait_for()
                    assert page.get_by_text(
                        "شروع Trailing SL",
                        exact=True,
                    ).count() == 0
                    trigger = page.locator(
                        ".field",
                        has_text="شروع Trailing",
                    ).locator("select")
                    assert trigger.locator("option").all_text_contents() == [
                        "TP1",
                        "TP2",
                        "TP3",
                    ]

                    # Work 5: Add Exchange modal must not white-screen.
                    page.locator("aside.sidebar").get_by_text(
                        "صرافی‌ها",
                        exact=True,
                    ).click()
                    page.get_by_role(
                        "button",
                        name="افزودن اتصال",
                    ).click()
                    page.get_by_role(
                        "heading",
                        name="افزودن اتصال صرافی",
                    ).wait_for()
                    page.get_by_text(
                        "راهنمای اتصال",
                        exact=True,
                    ).wait_for()
                    page.locator(".modal .iconBtn").click()

                    # Work 4: external trade details and management panel.
                    page.locator("aside.sidebar").get_by_text(
                        "معاملات",
                        exact=True,
                    ).click()
                    page.get_by_text(
                        "معاملات خارجی صرافی",
                        exact=True,
                    ).wait_for()
                    page.locator(
                        "table tbody tr",
                        has_text="BTC/USDT",
                    ).last.click()
                    page.get_by_role(
                        "heading",
                        name="جزئیات معامله خارجی",
                    ).wait_for()
                    page.get_by_text(
                        "اعمال مدیریت روی معامله",
                        exact=True,
                    ).wait_for()
                    page.get_by_text("Trailing SL", exact=True).last.wait_for()
                    page.locator(".drawer .iconBtn").first.click()

                    # Work 3: approve saves current review first, then transfers.
                    page.locator("aside.sidebar").get_by_text(
                        "صندوق سیگنال",
                        exact=True,
                    ).click()
                    page.locator(
                        ".signalSelectRow button",
                        has_text="BTC/USDT",
                    ).click()
                    page.get_by_role(
                        "button",
                        name="تأیید و انتقال به معامله",
                    ).click()
                    try:
                        page.get_by_role(
                            "heading",
                            name="معامله جدید",
                        ).wait_for(timeout=15000)
                    except Exception:
                        toast_text = ""
                        try:
                            toast_text = page.locator(".toast").inner_text(timeout=1000)
                        except Exception:
                            pass
                        action_error = ""
                        try:
                            action_error = page.locator(
                                ".actionBox .errorBox"
                            ).inner_text(timeout=1000)
                        except Exception:
                            pass
                        diagnostic = (
                            "Signal transfer failed; "
                            f"url={page.url!r}; "
                            f"hash={page.evaluate('location.hash')!r}; "
                            f"toast={toast_text!r}; "
                            f"action_error={action_error!r}; "
                            f"inbox_responses={inbox_responses!r}; "
                            f"page_errors={errors!r}"
                        )
                        page.screenshot(
                            path=str(
                                artifacts
                                / "stage27-signal-transfer-failure.png"
                            ),
                            full_page=True,
                        )
                        raise AssertionError(diagnostic) from None
                    page.locator(
                        ".marketSelectButton",
                        has_text="BTC / USDT",
                    ).wait_for()
                    assert page.locator(
                        ".field",
                        has_text="Entry",
                    ).locator("input").input_value().startswith("80000")

                    page.screenshot(
                        path=str(
                            artifacts / "stage27-trading-workflow-desktop.png"
                        ),
                        full_page=True,
                    )
                    if errors:
                        raise AssertionError(
                            "React page errors: " + " | ".join(errors)
                        )
                    browser.close()
                print(
                    "PASS Stage27 market picker/settings/exchange modal/"
                    "external detail/signal transfer smoke"
                )
            finally:
                web.terminate()
                try:
                    web.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    web.kill()


if __name__ == "__main__":
    main()
