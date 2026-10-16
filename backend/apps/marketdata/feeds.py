"""Public, read-only market quotes with bounded Redis caching and stale-state semantics.

Quotes are display-only in Stage 04: callers MUST NOT use this cache to fill orders.
"""
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.utils import timezone

from apps.exchanges.adapters import AdapterError, get_adapter

logger = logging.getLogger(__name__)
FRESH_SECONDS = 25
CACHE_SECONDS = 90
LOCK_SECONDS = 12
SUPPORTED_FEEDS = {"simulator", "binance"}


def _key(market_id):
    return f"marketdata:v1:quote:{int(market_id)}"


def _positive_decimal(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid exchange market amount") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError("Exchange market value must be finite and positive")
    return number


def _depth(levels):
    if not isinstance(levels, (tuple, list)) or len(levels) > 20:
        raise ValueError("Invalid order book depth")
    result = []
    for level in levels[:5]:
        if not isinstance(level, (tuple, list)) or len(level) != 2:
            raise ValueError("Invalid order book level")
        result.append([str(_positive_decimal(level[0])), str(_positive_decimal(level[1]))])
    return result


def get_quote(market, now=None):
    """Return an explicitly flagged quote or None; never synthesize a live quote."""
    now = now or timezone.now()
    item = cache.get(_key(market.pk))
    if not item:
        return None
    try:
        seen = datetime.fromisoformat(item["observed_at"])
        age = (now - seen).total_seconds()
    except (ValueError, TypeError, KeyError):
        return None
    # Future-dated provider response must never be treated as current.
    if age < -5:
        return None
    return {
        **item,
        "age_seconds": max(0, int(age)),
        "stale": age > FRESH_SECONDS,
        "trade_eligible": False,  # always display-only, even when fresh
    }


def refresh_quote(market):
    """Read public market data without using any user's Binance API credentials."""
    if not market.active or market.market_type != "spot":
        return {"status": "unsupported", "market_id": market.pk}
    adapter_code = market.exchange.adapter_code
    if adapter_code not in SUPPORTED_FEEDS:
        return {"status": "unsupported", "market_id": market.pk}
    lock_key = f"marketdata:v1:lock:{market.pk}"
    if not cache.add(lock_key, "1", timeout=LOCK_SECONDS):
        return {"status": "busy", "market_id": market.pk}
    try:
        adapter = get_adapter(adapter_code, credentials={}, environment="paper")
        ticker = adapter.fetch_ticker(market.symbol)
        price = _positive_decimal(ticker.price)
        if timezone.is_naive(ticker.observed_at):
            raise ValueError("Provider timestamp must be timezone-aware")
        # Reject delayed or future-dated values. They are not valid trade feeds.
        age = (timezone.now() - ticker.observed_at).total_seconds()
        if age < -5 or age > CACHE_SECONDS:
            raise ValueError("Stale provider ticker")
        book = adapter.fetch_orderbook(market.symbol)
        if book.get("symbol", "").upper() != market.symbol.upper():
            raise ValueError("Provider order book symbol mismatch")
        bids = _depth(book.get("bids", []))
        asks = _depth(book.get("asks", []))
        if bids and asks and Decimal(bids[0][0]) > Decimal(asks[0][0]):
            raise ValueError("Crossed book")
        payload = {
            "market_id": market.pk,
            "exchange": market.exchange.code,
            "symbol": market.symbol,
            "market_type": market.market_type,
            "price": str(price),
            "bid": bids[0][0] if bids else None,
            "ask": asks[0][0] if asks else None,
            "bids": bids,
            "asks": asks,
            "observed_at": ticker.observed_at.isoformat(),
            "source": adapter_code,
        }
        cache.set(_key(market.pk), payload, timeout=CACHE_SECONDS)
        return {"status": "ok", "market_id": market.pk, "data": get_quote(market)}
    except (AdapterError, ValueError, TypeError, KeyError, InvalidOperation):
        # Never log exception repr: HTTP transports can include signed URLs.
        logger.warning("Market feed failed", extra={"market_id": market.pk, "exchange": adapter_code})
        return {"status": "unavailable", "market_id": market.pk}
    finally:
        cache.delete(lock_key)
