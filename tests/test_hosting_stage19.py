"""Stage19 host capability and production operations checks."""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone


@pytest.mark.django_db
def test_host_capability_report_does_not_hide_missing_workers(monkeypatch):
    from apps.operations.hosting import hosting_capabilities

    monkeypatch.setattr(
        "apps.operations.hosting.dependency_status",
        lambda: {
            "postgresql": True,
            "redis_cache": True,
            "redis_broker": True,
            "redis_results": True,
        },
    )
    cache.delete("worker_heartbeat")
    report = hosting_capabilities()
    assert report["status"] == "incomplete"
    assert {"workers", "scheduler", "outbound_https", "storage"} <= set(report["missing"])
    assert report["telegram_listener"] == "reserved_for_stage21_not_running"


@pytest.mark.django_db
def test_host_capability_api_is_private_and_reports_fresh_queues(
    client, django_user_model, settings, monkeypatch
):
    from apps.operations.models import WorkerHeartbeat

    now = timezone.now()
    for queue in settings.OPERATION_QUEUES:
        WorkerHeartbeat.objects.create(queue=queue, seen_at=now, worker=f"{queue}@host")
    cache.set("worker_heartbeat", {"seen_at": now.isoformat()}, 95)
    monkeypatch.setattr(
        "apps.operations.hosting.dependency_status",
        lambda: {
            "postgresql": True,
            "redis_cache": True,
            "redis_broker": True,
            "redis_results": True,
        },
    )
    assert client.get(reverse("api-host-capabilities")).status_code == 302
    user = django_user_model.objects.create_user(username="host19")
    client.force_login(user)
    payload = client.get(reverse("api-host-capabilities")).json()
    workers = next(row for row in payload["capabilities"] if row["key"] == "workers")
    assert workers["ok"] is True and "7/7" in workers["evidence"]
    WorkerHeartbeat.objects.filter(queue=settings.OPERATION_QUEUES[0]).update(
        seen_at=now - timedelta(minutes=3)
    )
    assert client.get(reverse("api-host-capabilities")).status_code == 503


def test_public_https_probe_rejects_private_destination(settings):
    from apps.operations.hosting import _outbound_https
    from django.core.exceptions import ValidationError

    settings.HOSTING_EGRESS_PROBE_URL = "https://127.0.0.1/private"
    with pytest.raises(ValidationError):
        _outbound_https()
