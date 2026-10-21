"""Real service + browser smoke test. Run only against a disposable local development DB."""

import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
if os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith(("production", "staging")):
    raise SystemExit("Smoke must never run against production or staging.")
# Playwright's synchronous API owns an internal event loop. This disposable smoke
# runner is single-threaded, so allow its two ORM polls while that loop is active.
# Production web and worker processes never receive this setting.
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
import django  # noqa: E402

django.setup()
from apps.exchanges.models import (  # noqa: E402
    Asset,
    BalanceSnapshot,
    Exchange,
    ExchangeMarket,
    UserExchangeAccount,
)
from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.cache import cache  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.utils import timezone  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


def wait_for(check, seconds=45):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return
        time.sleep(0.25)
    raise AssertionError("Timed out waiting for service readiness.")


def main():
    if settings.DATABASES["default"]["HOST"] not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Smoke requires a disposable PostgreSQL database on localhost.")
    call_command("migrate", interactive=False, verbosity=0)
    call_command("collectstatic", interactive=False, verbosity=0)
    cache.delete("worker_heartbeat")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    processes, logs = [], []
    artifacts = ROOT / ".runtime" / "screenshots"
    artifacts.mkdir(parents=True, exist_ok=True)
    username = "smoke-" + secrets.token_hex(6)
    password = secrets.token_urlsafe(24)
    user = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@example.test",
        display_name="کاربر آزمون مرورگر",
        password=password,
    )
    env = dict(os.environ, PYTHONPATH=str(BACKEND))
    try:
        with tempfile.TemporaryDirectory(prefix="cryptosniper-smoke-") as work:

            def start(name, args):
                log = open(Path(work) / (name + ".log"), "w+")
                logs.append((name, log))
                processes.append(
                    subprocess.Popen(args, cwd=BACKEND, env=env, stdout=log, stderr=log)
                )

            for queue in settings.OPERATION_QUEUES:
                start(
                    queue,
                    [
                        sys.executable,
                        "-m",
                        "celery",
                        "-A",
                        "config",
                        "worker",
                        "--pool=solo",
                        "--concurrency=1",
                        "-Q",
                        queue,
                        "--without-gossip",
                        "--without-mingle",
                        "-n",
                        queue + "@%h",
                    ],
                )
            start(
                "beat",
                [
                    sys.executable,
                    "-m",
                    "celery",
                    "-A",
                    "config",
                    "beat",
                    "--schedule",
                    str(Path(work) / "beat"),
                    "--max-interval=2",
                ],
            )
            start(
                "web", [sys.executable, "manage.py", "runserver", "--noreload", f"127.0.0.1:{port}"]
            )
            base = f"http://127.0.0.1:{port}"

            def ready():
                try:
                    return httpx.get(base + "/health/ready/", timeout=5).status_code == 200
                except httpx.TransportError:
                    return False

            wait_for(ready)
            response = httpx.get(base + "/health/ready/")
            assert all(response.json()["checks"].values())
            print("PASS PostgreSQL + Redis cache/broker/results readiness")
            call_command("check_infrastructure", timeout=30)
            wait_for(lambda: bool(cache.get("worker_heartbeat")))
            print("PASS Beat dispatched heartbeat to maintenance Worker")
            exchange, _ = Exchange.objects.update_or_create(
                code="bitunix",
                defaults={
                    "name": "Bitunix",
                    "adapter_code": "bitunix",
                    "spot_supported": True,
                    "margin_supported": False,
                    "enabled": True,
                },
            )
            btc, _ = Asset.objects.get_or_create(symbol="BTC")
            usdt, _ = Asset.objects.get_or_create(symbol="USDT")
            smoke_market, _ = ExchangeMarket.objects.get_or_create(
                exchange=exchange,
                symbol="BTC/USDT",
                market_type="spot",
                defaults={
                    "base_asset": btc,
                    "quote_asset": usdt,
                    "active": True,
                    "synced_at": timezone.now(),
                },
            )
            account = UserExchangeAccount.objects.create(
                owner=user,
                exchange=exchange,
                label="Bitunix Smoke",
                environment="live",
                status="connected",
                permissions={"can_read": True, "can_trade_spot": True, "can_withdraw": False},
            )
            BalanceSnapshot.objects.create(
                exchange_account=account,
                asset=usdt,
                wallet_scope="spot",
                free_balance="220.51",
                locked_balance="0",
                total_balance="220.51",
                captured_at=timezone.now(),
            )
            cache.set(
                f"marketdata:v1:quote:{smoke_market.pk}",
                {
                    "market_id": smoke_market.pk,
                    "exchange": "bitunix",
                    "symbol": "BTC/USDT",
                    "market_type": "spot",
                    "price": "65000",
                    "bid": "64999",
                    "ask": "65001",
                    "bids": [],
                    "asks": [],
                    "observed_at": timezone.now().isoformat(),
                    "source": "smoke",
                },
                90,
            )

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                errors = []
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                manifest = page.request.get(base + "/manifest.webmanifest")
                worker_script = page.request.get(base + "/service-worker.js")
                assert manifest.ok and worker_script.ok
                assert "/api/" not in worker_script.text()

                page.goto(base + "/auth/login/")
                page.locator('[name="username"]').fill(username)
                page.locator('[name="password"]').fill(password)
                page.get_by_role("button", name="ورود به فضای کار").click()
                page.wait_for_url("**/dashboard/")
                page.locator("#cs-dashboard-root .cs-metrics").wait_for()
                page.get_by_text("تتر آزاد لحظه‌ای", exact=True).wait_for()
                page.screenshot(path=str(artifacts / "stage23-dashboard-desktop.png"), full_page=True)

                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(artifacts / "stage23-dashboard-mobile.png"), full_page=True)

                page.set_viewport_size({"width": 1440, "height": 1000})
                page.goto(base + "/manual/new/?account_id=" + str(account.pk) + "&market_id=" + str(smoke_market.pk))
                page.locator("#cs-manual-root").wait_for()
                page.get_by_text("Fix Loss", exact=True).wait_for()
                page.get_by_text("65000.00000000", exact=True).wait_for()
                page.screenshot(path=str(artifacts / "stage23-manual-desktop.png"), full_page=True)

                page.goto(base + "/exchanges/")
                page.locator("#cs-exchanges-root").wait_for()
                page.get_by_text("Bitunix Smoke", exact=True).wait_for()
                assert page.get_by_text("شبیه‌ساز CryptoSniper", exact=True).count() == 0
                page.screenshot(path=str(artifacts / "stage23-exchanges-desktop.png"), full_page=True)

                page.goto(base + "/watchlist/")
                page.locator("#cs-watchlist-root").wait_for()
                page.get_by_text("ارزهای اولویت‌دار", exact=True).wait_for()
                page.screenshot(path=str(artifacts / "stage23-watchlist-desktop.png"), full_page=True)

                page.goto(base + "/settings/profile/")
                page.get_by_role("heading", name="پروفایل و تنظیمات عمومی").wait_for()
                assert page.locator(".settings-tabs").count() == 1
                page.screenshot(path=str(artifacts / "stage23-settings-desktop.png"), full_page=True)

                assert not errors, errors
                browser.close()
            print("PASS Stage23 React shell, live dashboard, Manual, exchanges, watchlist and settings")
            print("PASS Beat dispatched heartbeat to maintenance Worker and browser had no JS errors")
            user.delete()
    except Exception:
        for name, log in logs:
            log.flush()
            log.seek(0)
            print(f"Diagnostic log: {name}\n" + log.read()[-5000:])
        raise
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for _, log in logs:
            log.close()
        get_user_model().objects.filter(pk=user.pk).delete()


if __name__ == "__main__":
    main()
