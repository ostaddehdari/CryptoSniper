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
    assert client.get(reverse("api-host-capabilities")).status_code == 401
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


@pytest.mark.django_db
def test_deployment_readiness_is_private_and_never_requires_node(
    client, django_user_model, settings, monkeypatch, tmp_path
):
    static_root = tmp_path / "staticfiles"
    static_root.mkdir()
    (static_root / "staticfiles.json").write_text("{}")
    settings.STATIC_ROOT = static_root
    settings.RELEASE_VERSION = "0.20.0rc1"
    settings.SOURCE_REVISION = "test-revision"
    monkeypatch.setattr(
        "apps.core.deployment.dependency_status",
        lambda: {
            "postgresql": True,
            "redis_cache": True,
            "redis_broker": True,
            "redis_results": True,
        },
    )
    assert client.get(reverse("api-deployment-readiness")).status_code == 302
    client.force_login(django_user_model.objects.create_user(username="deploy19"))
    payload = client.get(reverse("api-deployment-readiness")).json()
    assert payload["status"] == "ready"
    assert payload["release"] == "0.20.0rc1"
    assert payload["source_revision"] == "test-revision"
    assert payload["node_required"] is False
    assert payload["static"]["collected"] is True


@pytest.mark.django_db
def test_exact_deployment_check_sees_no_pending_migrations(settings, monkeypatch, tmp_path):
    from apps.core.deployment import deployment_status

    static_root = tmp_path / "staticfiles"
    static_root.mkdir()
    (static_root / "staticfiles.json").write_text("{}")
    settings.STATIC_ROOT = static_root
    monkeypatch.setattr(
        "apps.core.deployment.dependency_status",
        lambda: {
            "postgresql": True,
            "redis_cache": True,
            "redis_broker": True,
            "redis_results": True,
        },
    )
    status = deployment_status(include_migrations=True)
    assert status["status"] == "ready"
    assert status["migrations"] == {"current": True, "pending_count": 0}


@pytest.mark.django_db
def test_monitor_requires_every_queue_and_single_beat_receipt(settings, monkeypatch):
    from apps.operations.models import WorkerHeartbeat
    from apps.operations.monitoring import service_snapshot

    now = timezone.now()
    for queue in settings.OPERATION_QUEUES:
        WorkerHeartbeat.objects.create(queue=queue, seen_at=now, worker=f"{queue}@host")
    cache.set("worker_heartbeat", {"seen_at": now.isoformat()}, 95)
    monkeypatch.setattr(
        "apps.operations.monitoring._queue_depths",
        lambda: {queue: 0 for queue in settings.OPERATION_QUEUES},
    )
    snapshot = service_snapshot()
    assert snapshot["status"] == "healthy"
    assert snapshot["scheduler"] == {"fresh": True, "single_instance_lease": True}
    assert snapshot["telegram_listener"] == "reserved_disabled_until_stage21"
    WorkerHeartbeat.objects.filter(queue="orders").delete()
    assert service_snapshot()["status"] == "degraded"


@pytest.mark.django_db
def test_monitor_task_persists_snapshot_without_running_in_browser(settings, monkeypatch):
    from apps.operations.models import WorkerHeartbeat
    from apps.operations.tasks import monitor_services

    now = timezone.now()
    for queue in settings.OPERATION_QUEUES:
        WorkerHeartbeat.objects.create(queue=queue, seen_at=now, worker=f"{queue}@host")
    cache.set("worker_heartbeat", {"seen_at": now.isoformat()}, 95)
    monkeypatch.setattr(
        "apps.operations.monitoring._queue_depths",
        lambda: {queue: 0 for queue in settings.OPERATION_QUEUES},
    )
    result = monitor_services.run()
    assert result["status"] == "healthy"
    assert cache.get("operations:service-snapshot")["real_order_writes"] is False


def test_release_candidate_keeps_environment_and_live_boundary_explicit(settings, monkeypatch):
    from apps.operations.release import release_candidate_status

    settings.DEPLOYMENT_ENVIRONMENT = "staging"
    monkeypatch.setattr(
        "apps.operations.release.deployment_status", lambda **kwargs: {"status": "ready"}
    )
    monkeypatch.setattr(
        "apps.operations.release.hosting_capabilities", lambda **kwargs: {"status": "ready"}
    )
    monkeypatch.setattr("apps.operations.release.service_snapshot", lambda: {"status": "healthy"})
    result = release_candidate_status(probe_host=True)
    assert result["status"] == "ready"
    assert result["environment"] == "staging"
    assert result["real_order_writes"] is False
    assert result["telegram"] == "deferred_to_stage21"
    settings.DEPLOYMENT_ENVIRONMENT = "development"
    assert release_candidate_status()["status"] == "partial"
