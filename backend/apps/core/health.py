from django.conf import settings
from django.db import DatabaseError, connections
from redis import Redis
from redis.exceptions import RedisError


def dependency_status():
    """Bounded checks; never return connection URLs or exception contents."""
    status = {}
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            status["postgresql"] = cursor.fetchone()[0] == 1
    except DatabaseError:
        connections["default"].close()
        status["postgresql"] = False
    redis_urls = {"redis_cache": settings.REDIS_CACHE_URL}
    if hasattr(settings, "CELERY_BROKER_URL"):
        redis_urls.update(
            {
                "redis_broker": settings.CELERY_BROKER_URL,
                "redis_results": settings.CELERY_RESULT_BACKEND,
            }
        )
    for name, url in redis_urls.items():
        try:
            with Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1) as client:
                status[name] = bool(client.ping())
        except RedisError:
            status[name] = False
    return status
