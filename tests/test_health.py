from unittest.mock import patch

import pytest
from apps.core.health import dependency_status
from django.db import OperationalError, connection, connections
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError


def test_liveness_has_no_dependency_requirement(client):
    with patch("config.urls.dependency_status", side_effect=AssertionError):
        assert client.get("/health/live/").json()["status"] == "ok"


def test_readiness_reports_failure_without_leaking_credentials(client):
    with patch(
        "config.urls.dependency_status", return_value={"postgresql": False, "redis_cache": True}
    ):
        response = client.get("/health/ready/")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response["Cache-Control"] == "no-store"
    assert "password" not in response.content.decode()


@pytest.mark.django_db
def test_postgres_schema_is_utc_and_custom_user_exists(django_user_model):
    assert connection.vendor == "postgresql"
    user = django_user_model.objects.create_user(
        username="schema-test", password="some-long-password"
    )
    assert user.pk
    with connection.cursor() as cursor:
        cursor.execute("SHOW TIMEZONE")
        assert cursor.fetchone()[0] == "UTC"


@pytest.mark.django_db
def test_database_failure_is_bounded_and_sanitized():
    with patch.object(
        connections["default"], "cursor", side_effect=OperationalError("private-secret")
    ):
        assert dependency_status()["postgresql"] is False


@pytest.mark.django_db
def test_redis_failure_does_not_break_health(settings):
    with patch.object(Redis, "ping", side_effect=RedisConnectionError("private-secret")):
        result = dependency_status()
    assert result["postgresql"] is True
    assert result["redis_cache"] is False
