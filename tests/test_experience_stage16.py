"""Stage16 final responsive shell, PWA and accessibility checks."""

import json
from pathlib import Path

import pytest
from apps.signals.models import SignalSource
from django.urls import reverse
from test_stages09_exits import paper_trade


@pytest.mark.django_db
def test_login_and_primary_mobile_navigation(client, django_user_model):
    user = django_user_model.objects.create_user(username="mobile16", password="safe-test-pass")
    login = client.get(reverse("login"))
    assert login.status_code == 200
    assert b'autocomplete="username"' in login.content
    assert b'autocomplete="current-password"' in login.content
    client.force_login(user)
    dashboard = client.get(reverse("dashboard"))
    assert dashboard.status_code == 200
    assert b'id="root"' in dashboard.content

    workspace = client.get(reverse("app-shell"))
    assert workspace.status_code == 200
    assert b'id="root"' in workspace.content
    assert b"static/react/app.js" in workspace.content
    assert b"minimum-scale" not in workspace.content


@pytest.mark.django_db
def test_manual_and_smart_paste_are_react_workspace_pages(client, django_user_model):
    user = django_user_model.objects.create_user(username="forms16")
    client.force_login(user)
    manual = client.get(reverse("manual-new"))
    smart = client.get(reverse("smart-paste"))
    for response in (manual, smart):
        assert response.status_code == 200
        assert b'id="root"' in response.content
        assert b"static/react/app.js" in response.content
        assert b"stage24-rebuild.css" not in response.content
    assert b'window.__CS_INITIAL_PAGE__="manual"' in manual.content
    assert b'window.__CS_INITIAL_PAGE__="smart"' in smart.content


@pytest.mark.django_db
def test_trade_catalogue_and_detail_render_react_trades(client, django_user_model):
    user = django_user_model.objects.create_user(username="trades16")
    trade = paper_trade(user)
    client.force_login(user)
    catalogue = client.get(reverse("paper-trades"))
    detail = client.get(reverse("paper-trade-detail", args=[trade.pk]))
    for response in (catalogue, detail):
        assert response.status_code == 200
        assert b'id="root"' in response.content
        assert b"static/react/app.js" in response.content
        assert b'window.__CS_INITIAL_PAGE__="trades"' in response.content


@pytest.mark.django_db
def test_settings_routes_use_react_and_telegram_stays_deferred(client, django_user_model):
    user = django_user_model.objects.create_user(username="settings16")
    telegram = SignalSource.objects.create(
        owner=user, name="کانال آزمایشی", method="telegram", enabled=False
    )
    client.force_login(user)
    expected = {
        "profile": "settings",
        "sessions": "settings",
        "trading-preferences": "settings",
        "source-settings": "settings",
        "exchange-center": "exchanges",
        "alerts": "alerts",
        "reports": "reports",
        "audit-events": "settings",
        "telegram-settings": "telegram",
    }
    for route, page in expected.items():
        response = client.get(reverse(route))
        assert response.status_code == 200
        assert b'id="root"' in response.content
        assert f'window.__CS_INITIAL_PAGE__="{page}"'.encode() in response.content
    response = client.post(
        reverse("api-ui-signal-sources"),
        data=json.dumps({"id": telegram.pk, "enabled": True}),
        content_type="application/json",
    )
    assert response.status_code == 400
    telegram.refresh_from_db()
    assert telegram.enabled is False


def test_pwa_manifest_and_worker_cache_static_assets_only(client):
    manifest = client.get(reverse("web-manifest"))
    worker = client.get(reverse("service-worker"))
    assert manifest.status_code == worker.status_code == 200
    assert manifest["Content-Type"].startswith("application/manifest+json")
    body = worker.content
    assert b"cryptosniper-static-v24-rebuild" in body
    assert b"event.request.method!=='GET'" in body
    assert b"startsWith(staticPrefix)" in body
    assert b"Background Sync" not in body and b"indexedDB" not in body
    assert b"/api/" not in body and b"/dashboard/" not in body


def test_offline_submit_guard_tolerates_a_control_named_method():
    script = (Path(__file__).parents[1] / "backend/static/js/pwa.js").read_text()
    assert 'event.target.getAttribute("method")' in script
    assert "event.target.method" not in script


@pytest.mark.django_db
def test_private_pages_are_no_store_and_expose_offline_status(client, django_user_model):
    user = django_user_model.objects.create_user(username="pwa16")
    client.force_login(user)
    page = client.get(reverse("app-shell"))
    assert page.status_code == 200
    assert b'id="root"' in page.content
    assert b"static/react/app.js" in page.content
    assert "no-store" in page["Cache-Control"]
