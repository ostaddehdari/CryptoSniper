"""Bounded authenticated quotes, polling, and optional ASGI-only SSE."""
import asyncio
import json
from datetime import timedelta

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.security import session_api_required

from .feeds import get_quote
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


def _state(markets):
    return [{"market_id": market.pk, "symbol": market.symbol,
             "exchange": market.exchange.code, "quote": get_quote(market)}
            for market in markets]


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
    return JsonResponse({"markets": _state(markets), "display_only": True,
                         "as_of": timezone.now().isoformat()})


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
