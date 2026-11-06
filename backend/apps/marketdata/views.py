"""Bounded authenticated quotes, polling, and optional ASGI-only SSE."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
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

HEADER_TICKER_CACHE_KEY = "marketdata:v2:header-live"
HEADER_TICKER_LOCK_KEY = HEADER_TICKER_CACHE_KEY + ":refreshing"
HEADER_TICKER_FRESH_SECONDS = 5
HEADER_TICKER_STALE_SECONDS = 300
HEADER_QUOTE_STALE_SECONDS = 30

HEADER_QUOTES = (
    ("usdt_toman", "nobitex", "USDT/IRT", "نوبیتکس"),
    ("btc_usdt", "binance", "BTC/USDT", "Binance"),
)


def _quote_payload(adapter_code, symbol, source_label):
    ticker = get_adapter(adapter_code, credentials={}, environment="paper").fetch_ticker(symbol)
    observed_at = ticker.observed_at
    age_seconds = max(0, int((timezone.now() - observed_at).total_seconds()))
    return {
        "value": str(ticker.price),
        "source": adapter_code + "_public",
        "source_label": source_label,
        "observed_at": observed_at.isoformat(),
        "age_seconds": age_seconds,
        "status": "stale" if age_seconds > HEADER_QUOTE_STALE_SECONDS else "live",
    }


def _legacy_header_fields(payload):
    """Keep older clients working while React consumes the structured quotes."""
    quotes = payload.get("quotes", {})
    return {
        **payload,
        "usdt_toman": (quotes.get("usdt_toman") or {}).get("value"),
        "btc_usdt": (quotes.get("btc_usdt") or {}).get("value"),
        "sources": {
            key: quote.get("source") for key, quote in quotes.items() if quote.get("source")
        },
    }


def _header_ticker_value():
    cached = cache.get(HEADER_TICKER_CACHE_KEY)
    if cached:
        return _legacy_header_fields(cached)

    previous = cache.get(HEADER_TICKER_CACHE_KEY + ":stale") or {}
    if not cache.add(HEADER_TICKER_LOCK_KEY, "1", timeout=15):
        if previous:
            waiting = {
                **previous,
                "stale": True,
                "quotes": {
                    key: {**quote, "status": "stale"}
                    for key, quote in previous.get("quotes", {}).items()
                },
            }
            return _legacy_header_fields(waiting)
        return _legacy_header_fields(
            {
                "quotes": {
                    key: {
                        "value": None,
                        "source": adapter_code + "_public",
                        "source_label": source_label,
                        "observed_at": None,
                        "age_seconds": None,
                        "status": "unavailable",
                    }
                    for key, adapter_code, _symbol, source_label in HEADER_QUOTES
                },
                "fetched_at": timezone.now().isoformat(),
                "refresh_after_seconds": HEADER_TICKER_FRESH_SECONDS,
                "stale": True,
            }
        )
    payload = {
        "quotes": {},
        "fetched_at": timezone.now().isoformat(),
        "refresh_after_seconds": HEADER_TICKER_FRESH_SECONDS,
    }
    previous_quotes = previous.get("quotes", {})
    try:
        with ThreadPoolExecutor(max_workers=len(HEADER_QUOTES)) as executor:
            futures = {
                executor.submit(_quote_payload, adapter_code, symbol, source_label): (
                    key,
                    adapter_code,
                    source_label,
                )
                for key, adapter_code, symbol, source_label in HEADER_QUOTES
            }
            for future in as_completed(futures):
                key, adapter_code, source_label = futures[future]
                try:
                    payload["quotes"][key] = future.result()
                except (AdapterError, ValueError, TypeError, KeyError):
                    old_quote = previous_quotes.get(key)
                    payload["quotes"][key] = (
                        {**old_quote, "status": "stale"}
                        if old_quote and old_quote.get("value") is not None
                        else {
                            "value": None,
                            "source": adapter_code + "_public",
                            "source_label": source_label,
                            "observed_at": None,
                            "age_seconds": None,
                            "status": "unavailable",
                        }
                    )
    finally:
        cache.delete(HEADER_TICKER_LOCK_KEY)

    statuses = {quote["status"] for quote in payload["quotes"].values()}
    payload["stale"] = "stale" in statuses or "unavailable" in statuses

    cache.set(HEADER_TICKER_CACHE_KEY, payload, timeout=HEADER_TICKER_FRESH_SECONDS)
    if any(quote.get("value") is not None for quote in payload["quotes"].values()):
        cache.set(
            HEADER_TICKER_CACHE_KEY + ":stale",
            payload,
            timeout=HEADER_TICKER_STALE_SECONDS,
        )
    return _legacy_header_fields(payload)


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
