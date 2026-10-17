"""Batch read display quotes. Stale prices cannot masquerade as current valuation."""

from datetime import datetime
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone
from redis.exceptions import RedisError


def quotes_for(markets):
    markets = list(markets)
    keys = {f"marketdata:v1:quote:{m.pk}": m.pk for m in markets}
    try:
        values = cache.get_many(keys)
    except RedisError:
        return {}, False
    result = {}
    now = timezone.now()
    for key, data in values.items():
        try:
            price = Decimal(data["price"])
            observed = datetime.fromisoformat(data["observed_at"])
            age = (now - observed).total_seconds()
            if not price.is_finite() or price <= 0 or not -5 <= age <= 25:
                continue
            result[keys[key]] = {"price": price, "observed_at": observed, "source": data["source"]}
        except (ValueError, TypeError, KeyError, ArithmeticError):
            continue
    return result, True
