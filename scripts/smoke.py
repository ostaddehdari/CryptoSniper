"""Real service + browser smoke test. Run only against a disposable local development DB."""

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
if os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith(("production", "staging")):
    raise SystemExit("Smoke must never run against production or staging.")
# Playwright's synchronous API owns an internal event loop. This disposable smoke
# runner is single-threaded, so allow its two ORM polls while that loop is active.
# Production web and worker processes never receive this setting.
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
import django  # noqa: E402

django.setup()
from apps.core.models import ServiceProbe  # noqa: E402
from apps.exchanges.models import Exchange, ExchangeMarket, UserExchangeAccount  # noqa: E402
from apps.tradeplans.models import TradePlan  # noqa: E402
from apps.trading.models import Trade  # noqa: E402
from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.cache import cache  # noqa: E402
from django.core.management import call_command  # noqa: E402
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
                page.screenshot(path=str(artifacts / "login-desktop.png"), full_page=True)
                page.locator('[name="username"]').fill(username)
                page.locator('[name="password"]').fill(password)
                page.get_by_role("button", name="ورود به فضای کار").click()
                page.wait_for_url("**/dashboard/")
                page.locator("[data-cs24-root]").wait_for()
                page.get_by_role("heading", name="نمای کلی").wait_for()
                page.get_by_text("USDT / USD", exact=True).wait_for()
                page.get_by_text("USDT / تومان", exact=True).wait_for()
                assert page.locator(".s24-tickers a").count() == 0
                assert page.locator(".s24-sidebar").count() == 1
                page.locator("[data-overview-open]").wait_for()
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(artifacts / "dashboard13-mobile.png"), full_page=True)
                page.set_viewport_size({"width": 1440, "height": 1000})
                page.screenshot(path=str(artifacts / "dashboard-desktop.png"), full_page=True)
                page.goto(base + "/settings/profile/")
                page.get_by_role("heading", name="پروفایل").wait_for()
                page.screenshot(path=str(artifacts / "profile-desktop.png"), full_page=True)
                page.goto(base + "/settings/trading/")
                page.get_by_role("heading", name="پیش‌فرض‌های معامله").wait_for()
                assert Decimal(page.locator('[name="tp1_percent"]').input_value()) == Decimal("10")
                assert Decimal(page.locator('[name="tp2_percent"]').input_value()) == Decimal("10")
                assert Decimal(page.locator('[name="tp3_percent"]').input_value()) == Decimal("80")
                page.screenshot(path=str(artifacts / "trading-desktop.png"), full_page=True)
                page.goto(base + "/settings/security/audit/")
                page.get_by_role("heading", name="گزارش امنیتی حساب").wait_for()
                page.screenshot(path=str(artifacts / "security-desktop.png"), full_page=True)
                page.goto(base + "/exchanges/")
                page.get_by_role("heading", name="اتصال‌ها و حساب‌های صرافی").wait_for()
                page.screenshot(path=str(artifacts / "exchanges-empty-desktop.png"), full_page=True)
                page.get_by_role("link", name="افزودن اولین اتصال").click()
                page.get_by_label("صرافی").select_option(label="شبیه‌ساز CryptoSniper")
                page.get_by_label("نام این اتصال").fill("حساب تمرین مرورگر")
                page.get_by_role("button", name="ذخیره و بررسی امن اتصال").click()
                page.wait_for_url("**/exchanges/*/")
                page.get_by_role("heading", name="حساب تمرین مرورگر").wait_for()
                account = UserExchangeAccount.objects.get(owner=user)
                wait_for(
                    lambda: UserExchangeAccount.objects.get(pk=account.pk).status == "connected"
                )
                page.reload()
                page.get_by_text("BTC/USDT", exact=True).first.wait_for()
                page.screenshot(path=str(artifacts / "exchange-detail-desktop.png"), full_page=True)

                # Unified Cornix workspace must execute the real account -> market ->
                # chart -> draft path.
                smoke_market = ExchangeMarket.objects.get(
                    exchange=account.exchange, symbol="BTC/USDT", market_type="spot"
                )
                from apps.marketdata.models import HistoricalCandle
                from django.utils import timezone
                now = timezone.now()
                HistoricalCandle.objects.update_or_create(
                    provider="binance_public",
                    symbol="BTC/USDT",
                    interval="5m",
                    open_time=now - timedelta(minutes=5),
                    defaults={
                        "close_time": now,
                        "open_price": Decimal("64000"),
                        "high_price": Decimal("66000"),
                        "low_price": Decimal("63000"),
                        "close_price": Decimal("65000"),
                        "volume": Decimal("12"),
                    },
                )
                page.goto(base + "/app/#/newtrade")
                page.locator("[data-cs24-root]").wait_for()
                page.get_by_role("heading", name="معامله جدید").wait_for()
                with page.expect_response(
                    lambda res: "/api/v1/markets/search/" in res.url
                    and f"account={account.pk}" in res.url
                ) as market_response:
                    page.locator("[data-account-select]").select_option(str(account.pk))
                assert market_response.value.status == 200
                page.locator(f'[data-market-id="{smoke_market.pk}"]').wait_for()
                with page.expect_response(
                    lambda res: "/api/v1/markets/chart/" in res.url
                    and f"market={smoke_market.pk}" in res.url
                ) as chart_response:
                    page.locator(f'[data-market-id="{smoke_market.pk}"]').click()
                assert chart_response.value.status == 200
                page.locator('[data-newtrade-form] [name="entry_price"]').fill("65000")
                page.locator('[data-newtrade-form] [name="tp1"]').fill("70000")
                page.locator('[data-newtrade-form] [name="stop_loss"]').fill("60000")
                page.locator('[data-newtrade-form] [name="capital"]').fill("50")
                drafts_before = TradePlan.objects.filter(owner=user).count()
                with page.expect_response(
                    lambda res: "/api/v1/manual/plans/" in res.url
                    and res.request.method == "POST"
                ) as draft_response:
                    page.locator("[data-newtrade-form]").get_by_role(
                        "button", name="ساخت برنامه معامله"
                    ).click()
                assert draft_response.value.status in {200, 201}
                wait_for(
                    lambda: TradePlan.objects.filter(owner=user).count()
                    == drafts_before + 1
                )
                page.locator("[data-newtrade-status]").get_by_text(
                    "ساخته شد", exact=False
                ).wait_for()
                page.screenshot(
                    path=str(artifacts / "cornix-newtrade-real-draft.png"),
                    full_page=True,
                )
                print("PASS Cornix workspace real account -> market -> chart -> draft journey")

                page.goto(base + "/smart-paste/")
                page.get_by_role("heading", name="چسباندن هوشمند سیگنال").wait_for()
                page.locator('[name="text"]').fill(
                    "BTC/USDT LONG 🚀\nEntry: ۶۵۰۰۰\nTP1: 70000\nSL: 60000"
                )
                page.get_by_role("button", name="تحلیل و نمایش پیش‌نمایش").click()
                page.wait_for_url("**/inbox/*/")
                page.get_by_role("heading", name="پیشنهاد استخراج‌شده از متن").wait_for()
                page.screenshot(
                    path=str(artifacts / "smart-paste-preview-desktop.png"), full_page=True
                )
                page.locator('[name="account_id"]').select_option(str(account.pk))
                page.locator('[name="market_id"]').select_option(
                    str(
                        ExchangeMarket.objects.get(
                            exchange=account.exchange,
                            symbol="BTC/USDT",
                            market_type="spot",
                        ).pk
                    )
                )
                page.locator('[name="entry_price"]').fill("65000")
                page.locator('[name="stop_loss"]').fill("60000")
                page.locator('[name="tp1"]').fill("70000")
                page.locator("#id_reason").fill("تأیید بعد از بررسی متن اصلی")
                page.get_by_role("button", name="ذخیره اصلاحات و اعتبارسنجی").click()
                page.get_by_role("button", name="تأیید و انتقال به معامله").click()
                page.wait_for_url("**/manual/new/?signal=*")
                page.get_by_role("button", name="ذخیره پیش‌نویس و نمایش محاسبات").click()
                page.wait_for_url("**/manual/*/")
                page.get_by_role("button", name="تأیید و تثبیت Snapshot (بدون سفارش)").click()
                current_plan = TradePlan.objects.filter(owner=user).latest("pk")
                current_plan.refresh_from_db()
                if current_plan.status != "ready":
                    raise AssertionError(
                        f"SmartPaste plan={current_plan.status}, "
                        f"messages={page.locator('.notice').all_text_contents()}"
                    )
                page.get_by_role("button", name="ثبت درخواست اجرای Paper با تأیید من").click()
                if "/paper/" not in page.url or "/paper/launch/" in page.url:
                    raise AssertionError(
                        "Paper POST rejected: " + str(page.locator(".notice").all_text_contents())
                    )
                page.wait_for_url("**/paper/*/")
                paper = Trade.objects.filter(owner=user).latest("pk")
                wait_for(lambda: Trade.objects.get(pk=paper.pk).state == "open", seconds=45)
                page.screenshot(path=str(artifacts / "smart-paste-to-paper.png"), full_page=True)
                page.reload()
                page.get_by_role("heading", name="پوشش خروج و وضعیت Trailing").wait_for()
                page.get_by_role("button", name="شروع سناریوی قیمت دستی Paper", exact=False).click()
                page.get_by_role("button", name="ارسال Tick آزمایشی به موتور Paper").wait_for()
                page.locator('.paper-price-form [name="price"]').fill("80000")
                page.get_by_role("button", name="ارسال Tick آزمایشی به موتور Paper").click()
                page.get_by_role("heading", name="پوشش خروج و وضعیت Trailing").wait_for()
                assert Trade.objects.get(pk=paper.pk).state == "open"
                page.locator('.paper-price-form [name="price"]').fill("79100")
                page.get_by_role("button", name="ارسال Tick آزمایشی به موتور Paper").click()
                wait_for(lambda: Trade.objects.get(pk=paper.pk).state == "closed")
                from apps.reports.models import PerformanceAggregate, ReportRefreshState
                from apps.reports.tasks import rebuild_user

                rebuild_user.apply_async(args=[user.pk], queue="reports")
                wait_for(
                    lambda: (
                        ReportRefreshState.objects.filter(
                            owner=user, dirty_at__isnull=True
                        ).exists()
                        and PerformanceAggregate.objects.filter(owner=user).exists()
                    ),
                    seconds=45,
                )
                page.goto(base + "/reports/?period=day&group=total")
                page.get_by_role("heading", name="عملکرد و هزینه‌ها").wait_for()
                page.get_by_role("link", name="خروجی CSV").wait_for()
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(artifacts / "reports16-mobile.png"), full_page=True)
                page.set_viewport_size({"width": 1440, "height": 1000})
                page.screenshot(path=str(artifacts / "reports16-desktop.png"), full_page=True)
                assert user.timezone in page.content()
                print("PASS S20 alerts, notification, fee/P&L report and account timezone UI")
                page.goto(base + f"/paper/{paper.pk}/")
                page.screenshot(
                    path=str(artifacts / "paper-trailing-closed-desktop.png"), full_page=True
                )
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(
                    path=str(artifacts / "paper-trailing-closed-mobile.png"), full_page=True
                )
                page.set_viewport_size({"width": 1440, "height": 1000})
                # Independent second Paper trade: confirmed UI -> durable row -> orders Worker.
                import uuid

                from apps.trading.intent import queue_paper_trade
                from apps.trading.models import PaperExitFill, TradeAction

                managed, _ = queue_paper_trade(user, current_plan.pk, request_key=uuid.uuid4())
                wait_for(lambda: Trade.objects.get(pk=managed.pk).state == "open", seconds=45)
                page.goto(base + f"/paper/{managed.pk}/")
                page.locator('#close-remaining [name="confirmed"]').check()
                page.get_by_role("button", name="تأیید و ارسال بستن باقی‌مانده").click()
                wait_for(
                    lambda: TradeAction.objects.filter(trade=managed, state="done").exists(),
                    seconds=45,
                )
                assert (
                    PaperExitFill.objects.filter(trade=managed, reason="manual_close").count() == 1
                )
                page.reload()
                page.screenshot(path=str(artifacts / "manual-close14-desktop.png"), full_page=True)
                page.goto(base + "/paper/?tab=history")
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(artifacts / "history14-mobile.png"), full_page=True)
                page.goto(base + "/dashboard/")
                page.locator("[data-cs24-root]").wait_for()
                page.get_by_role("heading", name="نمای کلی").wait_for()
                page.get_by_text("USDT / USD", exact=True).wait_for()
                page.get_by_text("USDT / تومان", exact=True).wait_for()
                assert page.locator(".s24-tickers a").count() == 0
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(artifacts / "dashboard24-data-mobile.png"), full_page=True)
                print("PASS S24 rebuilt mobile dashboard + S14 confirmed close via orders Worker")
                page.set_viewport_size({"width": 1440, "height": 1000})
                page.goto(base + "/inbox/receive/")
                page.get_by_role("heading", name="ثبت متن اصلی سیگنال").wait_for()
                page.locator('[name="method"]').select_option("manual")
                page.locator('[name="text"]').fill(
                    "BTC/USDT\\nEntry: 65000\\nTP1: 70000\\nSL: 60000"
                )
                page.get_by_role("button", name="ثبت در Inbox بدون اجرای معامله").click()
                page.wait_for_url("**/inbox/*/")
                page.get_by_role("heading", name="بررسی سیگنال", exact=False).wait_for()
                page.screenshot(path=str(artifacts / "inbox-review-desktop.png"), full_page=True)
                page.locator('[name="account_id"]').select_option(str(account.pk))
                page.locator('[name="market_id"]').select_option(
                    page.locator('[name="market_id"] option')
                    .filter(has_text="BTC/USDT")
                    .first.get_attribute("value")
                )
                page.locator('[name="entry_price"]').fill("65000")
                page.locator('[name="stop_loss"]').fill("60000")
                page.locator('[name="tp1"]').fill("70000")
                page.locator("#id_reason").fill("بازبینی مرورگر")
                page.get_by_role("button", name="ذخیره اصلاحات و اعتبارسنجی").click()
                page.get_by_role("button", name="تأیید و انتقال به معامله").wait_for()
                for width in (320, 390, 768):
                    page.set_viewport_size({"width": width, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                        f"Signal Inbox overflow at {width}px"
                    )
                page.screenshot(path=str(artifacts / "inbox-review-mobile.png"), full_page=True)
                page.set_viewport_size({"width": 1440, "height": 1000})
                page.goto(base + "/manual/new/")
                page.get_by_role("heading", name="ورود دستی معامله").wait_for()
                page.locator('[name="account"]').select_option(str(account.pk))
                page.locator('[name="market"]').select_option(
                    label="BTC/USDT · Spot · شبیه‌ساز CryptoSniper"
                )
                page.locator('[name="entry_price"]').fill("65000")
                page.locator('[name="tp1"]').fill("70000")
                page.locator('[name="stop_loss"]').fill("60000")
                page.locator('[name="capital"]').fill("50")
                page.locator('[name="leverage"]').fill("1")
                page.get_by_role("button", name="ذخیره پیش‌نویس و نمایش محاسبات").click()
                page.wait_for_url("**/manual/*/")
                page.get_by_text("Quantity محاسبه‌شده").wait_for()
                page.screenshot(path=str(artifacts / "manual-preview-desktop.png"), full_page=True)
                page.get_by_role("button", name="تأیید و تثبیت Snapshot (بدون سفارش)").click()
                page.get_by_text("تأییدشده · فقط برای بررسی").wait_for()
                page.get_by_role("button", name="ثبت درخواست اجرای Paper با تأیید من").click()
                if "/paper/" not in page.url:
                    raise AssertionError(
                        f"Paper launch redirected to {page.url}; "
                        f"notices={page.locator('.notice').all_text_contents()}"
                    )
                page.wait_for_url("**/paper/*/")
                trade = Trade.objects.filter(owner=user).latest("pk")
                wait_for(
                    lambda: Trade.objects.get(pk=trade.pk).state == "open",
                    seconds=45,
                )
                page.goto(base + f"/paper/{trade.pk}/", wait_until="domcontentloaded")
                page.get_by_text("Position از Fillهای ثبت‌شده").wait_for()
                page.screenshot(path=str(artifacts / "paper-trade-desktop.png"), full_page=True)
                page.get_by_role("button", name="شروع سناریوی قیمت دستی Paper", exact=False).click()
                page.locator('.paper-price-form [name="price"]').fill("70000")
                page.get_by_role("button", name="ارسال Tick آزمایشی به موتور Paper").click()
                wait_for(lambda: Trade.objects.get(pk=trade.pk).state == "open", seconds=45)
                price_input = page.locator('.paper-price-form [name="price"]')
                price_input.wait_for(state="visible", timeout=15000)
                price_input.fill("69000")
                page.get_by_role("button", name="ارسال Tick آزمایشی به موتور Paper").click()
                wait_for(lambda: Trade.objects.get(pk=trade.pk).state == "closed", seconds=45)
                page.get_by_text("بسته‌شده", exact=False).first.wait_for(timeout=30000)
                print("PASS S20 Manual UI journey reached a closed Paper position")
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(artifacts / "manual-preview-mobile.png"), full_page=True)
                page.goto(base + "/manual/new/")
                page.set_viewport_size({"width": 320, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(artifacts / "manual-form-mobile.png"), full_page=True)
                page.set_viewport_size({"width": 1440, "height": 1000})
                page.goto(base + "/watchlist/")
                page.get_by_role("heading", name="دیده‌بان بازار").wait_for()
                page.get_by_role("button", name="＋").first.click()
                page.wait_for_url("**/watchlist/?list=*")
                page.get_by_text("BTC/USDT", exact=True).first.wait_for()
                page.screenshot(path=str(artifacts / "watchlist-desktop.png"), full_page=True)
                page.get_by_role("button", name="بروزرسانی").click()
                page.get_by_role("heading", name="دیده‌بان بازار").wait_for()
                for width in (320, 390, 768):
                    page.set_viewport_size({"width": width, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                        f"Watchlist overflow at {width}px"
                    )
                page.screenshot(path=str(artifacts / "watchlist-mobile.png"), full_page=True)
                page.set_viewport_size({"width": 1440, "height": 1000})
                page.goto(base + "/dashboard/")
                page.locator("[data-cs24-root]").wait_for()
                page.get_by_role("heading", name="نمای کلی").wait_for()
                for width in (320, 390, 768):
                    page.set_viewport_size({"width": width, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                        width
                    )
                page.screenshot(path=str(artifacts / "dashboard-mobile.png"), full_page=True)
                page.route("**/api/v1/dashboard/**", lambda route: route.abort())
                page.reload()
                page.locator("[data-overview-accounts]").wait_for()
                page.unroute("**/api/v1/dashboard/**")
                page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
                page.get_by_role("heading", name="نمای کلی").wait_for()
                page.locator("[data-overview-open]").wait_for(timeout=30000)
                print("PASS Cornix-like dashboard survives API interruption and reconnect")
                page.goto(base + "/exchanges/")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(artifacts / "exchanges-mobile.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                page.get_by_role("button", name="باز کردن منو").click()
                page.locator(".sidebar").get_by_role("link", name="وضعیت سرویس‌ها").click()
                page.wait_for_url("**/system/")
                page.get_by_text("ذخیره نتایج", exact=True).wait_for()
                page.screenshot(path=str(artifacts / "system-mobile.png"), full_page=True)
                with page.expect_response(
                    lambda res: res.url == base + "/system/probe/" and res.request.method == "POST"
                ):
                    page.get_by_role("button", name="بررسی Worker").click()
                # Stage11/12: real UI rule, then a simulator quote after browser closes.
                from apps.alerts.models import Notification, PriceAlert
                from apps.marketdata.feeds import refresh_quote
                from django.utils import timezone

                smoke_market = ExchangeMarket.objects.get(
                    exchange__code="simulator", symbol="BTC/USDT", market_type="spot"
                )
                refresh_quote(smoke_market)
                page.goto(base + "/alerts/new/")
                page.locator('[name="title"]').fill("هشدار مرورگر Stage12")
                page.locator('[name="market"]').select_option(str(smoke_market.pk))
                page.locator('[name="kind"]').select_option("price")
                page.locator('[name="direction"]').select_option("above")
                page.locator('[name="threshold"]').fill("66000")
                page.get_by_role("button", name="ذخیره هشدار", exact=True).click()
                page.wait_for_url("**/alerts/")
                page.get_by_role("heading", name="هشدار مرورگر Stage12").wait_for()
                alert = PriceAlert.objects.get(owner=user, title="هشدار مرورگر Stage12")
                page.screenshot(path=str(artifacts / "alerts-desktop.png"), full_page=True)
                for route in ("/alerts/", "/notifications/", "/operations/"):
                    page.goto(base + route)
                    for width in (320, 390, 768):
                        page.set_viewport_size({"width": width, "height": 844})
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth"
                        ), route
                    page.screenshot(
                        path=str(artifacts / (route.strip("/") + "-mobile.png")), full_page=True
                    )
                page.close()
                payload = cache.get(f"marketdata:v1:quote:{smoke_market.pk}")
                payload.update(price="67000", observed_at=timezone.now().isoformat())
                cache.set(f"marketdata:v1:quote:{smoke_market.pk}", payload, 90)
                wait_for(
                    lambda: Notification.objects.filter(owner=user, event__alert=alert).exists()
                )
                assert Notification.objects.filter(owner=user, event__alert=alert).count() == 1
                page = context.new_page()
                page.goto(base + "/notifications/")
                page.get_by_role("heading", name="هشدار مرورگر Stage12").wait_for()
                page.get_by_role("button", name="خواندم", exact=True).first.click()
                page.close()
                print(
                    "PASS alert UI and independent Worker after browser close; "
                    "notification read and mobile operations"
                )
                assert not errors, errors
                browser.close()
            # Browser and its page have now closed; server and Worker continue independently.
            wait_for(
                lambda: ServiceProbe.objects.filter(requested_by=user, status="succeeded").exists()
            )
            print("PASS desktop/mobile login, HTMX, Alpine, no overflow, no JS errors")
            print("PASS browser closed; Worker receipt persisted independently")
            user.delete()
            Exchange.objects.filter(code__in=("simulator", "binance")).update(enabled=True)
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
