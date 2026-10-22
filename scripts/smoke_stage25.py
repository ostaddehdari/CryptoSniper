"""Stage25 React browser smoke against disposable local PostgreSQL/Redis.

This smoke never creates exchange credentials and never submits an order.
"""

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
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.management import call_command  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


def wait_for(check, seconds=35):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return
        time.sleep(0.25)
    raise AssertionError("Timed out waiting for Stage25 smoke readiness.")


def main():
    if settings.DATABASES["default"]["HOST"] not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Stage25 smoke requires disposable local PostgreSQL.")

    call_command("migrate", interactive=False, verbosity=0)
    call_command("collectstatic", interactive=False, verbosity=0)

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    username = "stage25-" + secrets.token_hex(5)
    password = secrets.token_urlsafe(22)
    get_user_model().objects.create_user(
        username=username,
        password=password,
        display_name="کاربر آزمون Stage25",
    )

    env = dict(os.environ, PYTHONPATH=str(BACKEND))
    artifacts = ROOT / ".runtime" / "screenshots"
    artifacts.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cryptosniper-stage25-") as work:
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
                        return httpx.get(base + "/health/ready/", timeout=3).status_code == 200
                    except httpx.TransportError:
                        return False

                wait_for(ready)
                response = httpx.get(base + "/health/ready/", timeout=5)
                assert response.status_code == 200
                assert all(response.json()["checks"].values())

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
                    page.wait_for_url("**/app/")
                    page.get_by_role("heading", name="نمای کلی").wait_for()
                    page.get_by_text("حساب‌های متصل", exact=True).wait_for()
                    page.get_by_text("سفارش‌های واقعی", exact=True).wait_for()

                    sidebar = page.locator("aside.sidebar")
                    for label in (
                        "نمای کلی",
                        "معاملات",
                        "صندوق سیگنال",
                        "صرافی‌ها",
                        "تلگرام و سیگنال‌ها",
                        "هشدارها",
                        "گزارش‌ها",
                        "وضعیت سیستم",
                        "تنظیمات",
                    ):
                        assert sidebar.get_by_text(label, exact=True).count() == 1

                    for removed in (
                        "معامله دستی",
                        "تحلیل سیگنال",
                        "برنامه‌های معامله",
                        "کیف پول‌ها و راهنما",
                        "دیده‌بان و بازارها",
                    ):
                        assert sidebar.get_by_text(removed, exact=True).count() == 0

                    page.get_by_role("button", name="معامله جدید").first.click()
                    page.get_by_role("button", name="معامله دستی", exact=True).wait_for()
                    page.get_by_role("button", name="تحلیل سیگنال", exact=True).wait_for()
                    page.get_by_text("Fix Loss خودکار", exact=True).wait_for()
                    page.get_by_text("Trailing TP", exact=True).wait_for()
                    page.get_by_text("Trailing SL", exact=True).wait_for()
                    assert page.get_by_role("button", name="ارسال سفارش", exact=True).count() == 1
                    assert page.get_by_role("button", name="ذخیره برنامه TP/SL").count() == 0

                    page.locator("aside.sidebar").get_by_text("تنظیمات", exact=True).click()
                    page.get_by_role("button", name="پیش‌فرض معامله", exact=True).wait_for()
                    page.get_by_role("button", name="ارزهای منتخب", exact=True).wait_for()

                    page.locator("aside.sidebar").get_by_text("معاملات", exact=True).click()
                    page.get_by_role("button", name="معامله جدید", exact=True).wait_for()
                    page.get_by_text("معاملات و سفارش‌ها", exact=True).wait_for()

                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.screenshot(
                        path=str(artifacts / "stage25-trades-mobile.png"),
                        full_page=True,
                    )

                    page.set_viewport_size({"width": 1440, "height": 1000})
                    page.locator("aside.sidebar").get_by_text("نمای کلی", exact=True).click()
                    page.screenshot(
                        path=str(artifacts / "stage25-dashboard-desktop.png"),
                        full_page=True,
                    )

                    if errors:
                        raise AssertionError("React page errors: " + " | ".join(errors))
                    browser.close()

                print("PASS Stage25 React login/dashboard/sidebar/new-trade/settings/trades smoke")
            finally:
                web.terminate()
                try:
                    web.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    web.kill()
                log.flush()
                if web.returncode not in {0, -15, -9, None}:
                    log.seek(0)
                    print(log.read(), file=sys.stderr)


if __name__ == "__main__":
    main()
