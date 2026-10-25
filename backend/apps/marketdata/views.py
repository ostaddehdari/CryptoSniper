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
from apps.exchanges.models import UserExchangeAccount

from .feeds import get_quote
from .search import eligible_markets, search_markets

HEADER_TICKER_CACHE_KEY = "marketdata:v1:header-usdt"
HEADER_TICKER_FRESH_SECONDS = 20
HEADER_TICKER_STALE_SECONDS = 300


def _header_ticker_value():
    cached = cache.get(HEADER_TICKER_CACHE_KEY)
    if cached:
        return {**cached, "stale": False}

    stale = cache.get(HEADER_TICKER_CACHE_KEY + ":stale")
    payload = {
        "usdt_usd": None,
        "usdt_toman": None,
        "sources": {},
        "observed_at": timezone.now().isoformat(),
        "stale": False,
    }
    try:
        adapter = get_adapter("binance", credentials={}, environment="paper")
        ticker = adapter.fetch_ticker("USDT/USDC")
        payload["usdt_usd"] = str(ticker.price)
        payload["sources"]["usdt_usd"] = "binance_public"
    except (AdapterError, ValueError, TypeError, KeyError):
        pass

    try:
        adapter = get_adapter("nobitex", credentials={}, environment="paper")
        ticker = adapter.fetch_ticker("USDT/IRT")
        payload["usdt_toman"] = str(ticker.price)
        payload["sources"]["usdt_toman"] = "nobitex_public"
    except (AdapterError, ValueError, TypeError, KeyError):
        pass

    if payload["usdt_usd"] is None and stale:
        payload["usdt_usd"] = stale.get("usdt_usd")
    if payload["usdt_toman"] is None and stale:
        payload["usdt_toman"] = stale.get("usdt_toman")

    if payload["usdt_usd"] is None and payload["usdt_toman"] is None:
        if stale:
            return {**stale, "stale": True}
        return payload

    cache.set(HEADER_TICKER_CACHE_KEY, payload, timeout=HEADER_TICKER_FRESH_SECONDS)
    cache.set(HEADER_TICKER_CACHE_KEY + ":stale", payload, timeout=HEADER_TICKER_STALE_SECONDS)
    return payload


@session_api_required
@never_cache
@require_GET
def api_header_ticker(request):
    return JsonResponse({**_header_ticker_value(), "display_only": True})


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


def _state(markets):
    return [
        {
            "market_id": market.pk,
            "symbol": market.symbol,
            "exchange": market.exchange.code,
            "quote": get_quote(market),
        }
        for market in markets
    ]


@session_api_required
@never_cache
@require_GET
def api_search(request):
    account_id = request.GET.get("account")
    exchange_id = None
    if account_id:
        if not account_id.isascii() or not account_id.isdecimal():
            return JsonResponse({"error": "invalid_account"}, status=400)
        account = (
            UserExchangeAccount.objects.for_user(request.user)
            .select_related("exchange")
            .filter(
                pk=int(account_id),
                status__in=(
                    UserExchangeAccount.Status.CONNECTED,
                    UserExchangeAccount.Status.RESTRICTED,
                ),
            )
            .first()
        )
        if not account:
            return JsonResponse({"error": "account_not_found"}, status=404)
        if account.permissions.get("can_read") is not True:
            return JsonResponse({"error": "market_read_permission_required"}, status=403)
        exchange_id = account.exchange_id

    results = search_markets(
        request.user,
        request.GET.get("q", ""),
        limit=100 if account_id else 30,
        exchange_id=exchange_id,
    )
    return JsonResponse(
        {
            "results": results,
            "mode": "display_only",
            "account": int(account_id) if account_id else None,
        }
    )


@session_api_required
@never_cache
@require_GET
def api_quotes(request):
    markets = _visible(request)
    if markets is None:
        return JsonResponse({"error": "invalid_market_ids"}, status=400)
    return JsonResponse(
        {"markets": _state(markets), "display_only": True, "as_of": timezone.now().isoformat()}
    )


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
