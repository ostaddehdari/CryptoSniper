"""User-owned watchlists with enforced exchange-account visibility."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.security import session_api_required
from apps.exchanges.models import ExchangeMarket

from .feeds import get_quote
from .models import Watchlist, WatchlistItem
from .search import eligible_markets, market_is_readable, search_markets
from .tasks import refresh_market


def _owned_watchlist(request, pk):
    return get_object_or_404(Watchlist.objects.filter(owner=request.user), pk=pk)


@login_required
@never_cache
@require_GET
def watchlist_page(request):
    lists = list(Watchlist.objects.filter(owner=request.user))
    if not lists:
        lists = [Watchlist.objects.create(owner=request.user, name="منتخب من")]
    active = next((item for item in lists if str(item.pk) == request.GET.get("list")), lists[0])
    # Entries tied to disconnected accounts remain in the DB, but never leak prices.
    allowed = eligible_markets(request.user)
    entries = list(
        WatchlistItem.objects.filter(watchlist=active, market__in=allowed).select_related(
            "market", "market__exchange"
        )[:100]
    )
    for entry in entries:
        entry.quote = get_quote(entry.market)
    return render(
        request,
        "marketdata/watchlists.html",
        {
            "nav": "watchlist",
            "watchlists": lists,
            "active": active,
            "entries": entries,
            "search_results": search_markets(request.user, request.GET.get("q", ""), 20),
        },
    )


@login_required
@require_POST
def create_watchlist(request):
    name = str(request.POST.get("name", "")).strip()
    if not 1 <= len(name) <= 64:
        messages.error(request, "نام فهرست باید بین ۱ تا ۶۴ حرف باشد.")
        return redirect("watchlists")
    try:
        item = Watchlist.objects.create(owner=request.user, name=name)
    except IntegrityError:
        messages.error(request, "فهرستی با این نام از قبل وجود دارد.")
        return redirect("watchlists")
    return redirect(reverse("watchlists") + f"?list={item.pk}")


@login_required
@require_POST
def add_watchlist_item(request, pk):
    watchlist = _owned_watchlist(request, pk)
    try:
        market_id = int(request.POST.get("market_id", ""))
    except (ValueError, TypeError):
        messages.error(request, "بازار انتخاب‌شده معتبر نیست.")
        return redirect("watchlists")
    market = get_object_or_404(ExchangeMarket, pk=market_id)
    if not market_is_readable(request.user, market):
        messages.error(request, "ابتدا یک حساب خواندنی از این صرافی متصل کنید.")
        return redirect("watchlists")
    if watchlist.items.count() >= 100:
        messages.error(request, "هر فهرست حداکثر ۱۰۰ بازار دارد.")
        return redirect("watchlists")
    WatchlistItem.objects.get_or_create(watchlist=watchlist, market=market)
    return redirect(reverse("watchlists") + f"?list={watchlist.pk}")


@login_required
@require_POST
def remove_watchlist_item(request, pk, item_id):
    watchlist = _owned_watchlist(request, pk)
    get_object_or_404(WatchlistItem, watchlist=watchlist, pk=item_id).delete()
    return redirect(reverse("watchlists") + f"?list={watchlist.pk}")


@session_api_required
@never_cache
@require_GET
def api_watchlist(request, pk):
    watchlist = _owned_watchlist(request, pk)
    allowed = eligible_markets(request.user)
    entries = WatchlistItem.objects.filter(watchlist=watchlist, market__in=allowed).select_related(
        "market", "market__exchange"
    )[:100]
    return JsonResponse(
        {
            "watchlist_id": watchlist.pk,
            "display_only": True,
            "items": [
                {
                    "id": item.pk,
                    "market_id": item.market.pk,
                    "symbol": item.market.symbol,
                    "exchange": item.market.exchange.code,
                    "quote": get_quote(item.market),
                }
                for item in entries
            ],
        }
    )


@login_required
@require_POST
def request_market_refresh(request, pk, market_id):
    _owned_watchlist(request, pk)
    market = get_object_or_404(ExchangeMarket, pk=market_id)
    if not market_is_readable(request.user, market):
        messages.error(request, "برای این بازار اتصال مجاز ندارید.")
        return redirect("watchlists")
    throttle = f"marketdata:v1:manual:{request.user.pk}:{market.pk}"
    if cache.add(throttle, "1", timeout=20):
        refresh_market.apply_async(args=[market.pk], queue="maintenance")
        messages.success(request, "به‌روزرسانی قیمت در صف قرار گرفت.")
    else:
        messages.info(request, "لطفاً برای به‌روزرسانی مجدد کمی صبر کنید.")
    return redirect(reverse("watchlists") + f"?list={pk}")
