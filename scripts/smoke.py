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
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
import django  # noqa: E402

django.setup()
from apps.core.models import ServiceProbe  # noqa: E402
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
    user = get_user_model().objects.create_user(username=username, password=password)
    env = dict(os.environ, PYTHONPATH=str(BACKEND))
    try:
        with tempfile.TemporaryDirectory(prefix="cryptosniper-smoke-") as work:

            def start(name, args):
                log = open(Path(work) / (name + ".log"), "w+")
                logs.append((name, log))
                processes.append(
                    subprocess.Popen(args, cwd=BACKEND, env=env, stdout=log, stderr=log)
                )

            for queue in ("orders", "reports", "maintenance"):
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
                page.goto(base + "/auth/login/")
                page.screenshot(path=str(artifacts / "login-desktop.png"), full_page=True)
                page.locator('[name="username"]').fill(username)
                page.locator('[name="password"]').fill(password)
                page.get_by_role("button", name="ورود به فضای کار").click()
                page.wait_for_url("**/dashboard/")
                page.get_by_text("ذخیره نتایج", exact=True).wait_for()
                page.screenshot(path=str(artifacts / "dashboard-desktop.png"), full_page=True)
                for width in (320, 390, 768):
                    page.set_viewport_size({"width": width, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                        width
                    )
                page.screenshot(path=str(artifacts / "dashboard-mobile.png"), full_page=True)
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
                page.close()
                assert not errors, errors
                browser.close()
            # Browser and its page have now closed; server and Worker continue independently.
            wait_for(
                lambda: ServiceProbe.objects.filter(requested_by=user, status="succeeded").exists()
            )
            print("PASS desktop/mobile login, HTMX, Alpine, no overflow, no JS errors")
            print("PASS browser closed; Worker receipt persisted independently")
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
