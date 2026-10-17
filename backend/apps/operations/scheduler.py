"""Only the leased Beat instance publishes scheduled tasks; fail closed on Redis loss."""

import secrets

from celery.beat import PersistentScheduler
from redis.exceptions import RedisError

from .leases import RENEW, client


class LeasedScheduler(PersistentScheduler):
    def __init__(self, *args, **kwargs):
        self.lease_token = secrets.token_hex(20)
        super().__init__(*args, **kwargs)

    def tick(self, *args, **kwargs):
        connection = client()
        key = "cs:lease:beat"
        try:
            held = connection.eval(RENEW, 1, key, self.lease_token, 15)
            if not held:
                held = connection.set(key, self.lease_token, nx=True, ex=15)
            if not held:
                return 2.0
            return min(super().tick(*args, **kwargs), 2.0)
        except RedisError:
            return 2.0
