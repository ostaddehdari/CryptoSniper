"""Redis leases reduce overlap; PostgreSQL fencing/unique ledgers decide outcomes."""

import secrets
from contextlib import contextmanager

from django.conf import settings
from redis import Redis

RELEASE = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"  # noqa: E501
RENEW = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('expire',KEYS[1],ARGV[2]) else return 0 end"  # noqa: E501


def client():
    return Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=1, socket_timeout=1)


@contextmanager
def lease(name, seconds=50):
    connection = client()
    key, token = "cs:lease:" + name, secrets.token_hex(20)
    acquired = connection.set(key, token, nx=True, ex=seconds)
    try:
        yield bool(acquired)
    finally:
        if acquired:
            try:
                connection.eval(RELEASE, 1, key, token)
            except Exception:
                pass  # Expiry releases the lease; no financial decision depends on this deletion.
