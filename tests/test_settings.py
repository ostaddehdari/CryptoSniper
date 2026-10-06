import os
import subprocess
import sys

import pytest


def setting_result(module, **changes):
    env = dict(os.environ, DJANGO_SETTINGS_MODULE=module, PYTHONPATH="backend")
    env.update(changes)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from django.conf import settings; "
            "print(settings.DEBUG, settings.SESSION_COOKIE_SECURE)",
        ],
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("value", ["", "short"])
def test_missing_or_weak_secret_fails_closed(value):
    result = setting_result("config.settings.development", DJANGO_SECRET_KEY=value)
    assert result.returncode != 0


def test_sqlite_is_rejected():
    result = setting_result(
        "config.settings.development", DATABASE_URL="sqlite:///unwanted.sqlite3"
    )
    assert result.returncode != 0
    assert "requires PostgreSQL" in result.stderr


def test_production_is_secure_and_rejects_wildcard_hosts():
    result = setting_result("config.settings.production", DJANGO_ALLOWED_HOSTS="workspace.example")
    assert result.returncode == 0
    assert result.stdout.strip() == "False True"
    assert setting_result("config.settings.production", DJANGO_ALLOWED_HOSTS="*").returncode != 0
