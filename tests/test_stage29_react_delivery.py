from pathlib import Path

import pytest
from apps.core.assets import asset_url
from django.test import override_settings
from django.urls import reverse


def test_asset_updates_change_url_without_touching_static_path(tmp_path, monkeypatch):
    asset = tmp_path / "app.js"
    asset.write_text("first release")
    monkeypatch.setattr("apps.core.assets.finders.find", lambda name: str(asset))
    with override_settings(STATIC_URL="/another-prefix/static/"):
        old = asset_url("react/app.js")
        asset.write_text("replacement React release")
        new = asset_url("react/app.js")
    assert old != new
    assert new.startswith("/another-prefix/static/react/app.js?v=")


def test_pwa_retires_only_its_own_caches_and_versions_react(client):
    response = client.get(reverse("service-worker"))
    source = response.content.decode()
    assert response.status_code == 200
    assert "k.startsWith('cryptosniper-static-')" in source
    assert "self.skipWaiting()" in source
    assert "react/app.js?v=" in source
    assert "react/app.css?v=" in source
    assert "event.request.method!=='GET'" in source
    assert "!url.pathname.startsWith(staticPrefix)" in source


@pytest.mark.django_db
@pytest.mark.parametrize("route", ["home", "app-shell", "dashboard", "exchange-center", "inbox"])
def test_primary_pages_use_versioned_assets_and_never_serve_stage24_shell(
    client, django_user_model, route
):
    user = django_user_model.objects.create_user(username=f"s29-{route}")
    client.force_login(user)
    response = client.get(reverse(route))
    assert response.status_code == 200
    assert b'id="root"' in response.content
    assert b"react/app.js?v=" in response.content
    assert b"react/app.css?v=" in response.content
    for old_asset in (b"stage24-rebuild.js", b"stage24-rebuild.css", b"cornix-shell.js"):
        assert old_asset not in response.content


def test_finalization_plan_defines_five_stages_without_claiming_future_work_done():
    import json

    root = Path(__file__).resolve().parents[1]
    plan = json.loads((root / "docs/plan.json").read_text())
    final = [s for s in plan["stages"] if s["id"] in plan["finalization_stages"]]
    assert [s["id"] for s in final] == ["S29", "S30", "S31", "S32", "S33"]
    assert all(len(s["works"]) == 5 for s in final)
    current = int(json.loads((root / "docs/progress.json").read_text())["current_stage"][1:])
    assert all(s["status"] == "not_started" for s in final if s["number"] > current)
