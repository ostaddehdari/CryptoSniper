"""Bounded authenticated quotes, polling, and optional ASGI-only SSE."""

import asyncio
import json
from datetime import timedelta

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.security import session_api_required
from apps.exchanges.adapters import AdapterError, get_adapter

from .feeds import get_live_quote, get_quote, refresh_live_quote, refresh_quote
from .search import eligible_markets, search_markets


def _market_ids(request):
    raw = request.GET.getlist("market")
    if len(raw) > 20 or any(not value.isascii() or not value.isdecimal() for value in raw):
        return None
    return [int(v) for v in raw if len(v) < 15]


def _visible(request):
    ids = _market_ids(request)
    if ids is None:
        return None
    return list(eligible_markets(request.user).filter(pk__in=ids)[:20])


def _state(markets, *, live=False):
    getter = get_live_quote if live else get_quote
    return [
        {
            "market_id": market.pk,
            "symbol": market.symbol,
            "exchange": market.exchange.code,
            "quote": getter(market),
        }
        for market in markets
    ]


@session_api_required
@never_cache
@require_GET
def api_search(request):
    results = search_markets(request.user, request.GET.get("q", ""))
    return JsonResponse({"results": results, "mode": "display_only"})


@session_api_required
@never_cache
@require_GET
def api_quotes(request):
    markets = _visible(request)
    if markets is None:
        return JsonResponse({"error": "invalid_market_ids"}, status=400)
    live = request.GET.get("live") in {"1", "true", "yes"}
    for market in markets:
        if live:
            quote = get_live_quote(market)
            if not quote or quote.get("stale"):
                refresh_live_quote(market)
        else:
            quote = get_quote(market)
            if not quote or quote.get("stale"):
                refresh_quote(market)
    return JsonResponse(
        {
            "markets": _state(markets, live=live),
            "display_only": True,
            "live": live,
            "as_of": timezone.now().isoformat(),
        }
    )


@session_api_required
@never_cache
@require_GET
def api_public_prices(request):
    """Two explicit public reference prices for the global header.

    BTC/USDT comes from Bitunix Spot. USDT/IRT comes from Nobitex public orderbook.
    A failed provider is returned as unavailable; no synthetic fallback is emitted.
    """

    cache_key = "marketdata:v2:public-header"
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached)

    specs = (
        ("btc_usdt", "bitunix", "BTC/USDT"),
        ("usdt_irt", "nobitex", "USDT/IRT"),
    )
    prices = {}
    now = timezone.now()
    for key, adapter_code, symbol in specs:
        try:
            ticker = get_adapter(
                adapter_code,
                credentials={},
                environment="paper",
            ).fetch_ticker(symbol)
            age = (now - ticker.observed_at).total_seconds()
            if age < -5 or age > 30:
                raise ValueError("stale provider timestamp")
            prices[key] = {
                "symbol": symbol,
                "price": str(ticker.price),
                "source": adapter_code,
                "observed_at": ticker.observed_at.isoformat(),
                "age_seconds": max(0, round(age, 3)),
                "stale": age > 3,
            }
        except (AdapterError, ValueError, TypeError):
            prices[key] = {
                "symbol": symbol,
                "price": None,
                "source": adapter_code,
                "observed_at": None,
                "age_seconds": None,
                "stale": True,
                "unavailable": True,
            }
    payload = {"prices": prices, "as_of": now.isoformat()}
    cache.set(cache_key, payload, timeout=2)
    return JsonResponse(payload)


@session_api_required
@never_cache
@require_GET
def api_stream(request):
    # WSGI workers must NEVER block in an SSE loop: polling is the production fallback.
    if not getattr(settings, "MARKETDATA_SSE_ENABLED", False):
        return JsonResponse({"error": "sse_disabled", "fallback": "polling"}, status=409)
    markets = _visible(request)
    if markets is None:
        return JsonResponse({"error": "invalid_market_ids"}, status=400)
    if len(markets) > 10:
        return JsonResponse({"error": "stream_limit"}, status=429)

    async def stream():
        deadline = timezone.now() + timedelta(seconds=65)
        while timezone.now() < deadline:
            quotes = await sync_to_async(_state, thread_sensitive=True)(markets)
            payload = json.dumps({"markets": quotes, "display_only": True}, ensure_ascii=False)
            yield f"event: quotes\ndata: {payload}\n\n"
            await asyncio.sleep(10)
        yield "event: reconnect\ndata: {}\n\n"

    response = StreamingHttpResponse(stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-store, no-transform"
    response["X-Accel-Buffering"] = "no"
    return response
