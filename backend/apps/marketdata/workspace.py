"""Owner-scoped, paginated market selection and per-exchange favorites."""

import json
import re

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.security import session_api_required
from apps.exchanges.models import ExchangeMarket, UserExchangeAccount

from .models import ExchangeFavorite


def owned_exchange(user, code):
    account = (
        UserExchangeAccount.objects.for_user(user)
        .exclude(status="disabled")
        .filter(exchange__code=str(code))
        .select_related("exchange")
        .order_by("pk")
        .first()
    )
    if account is None:
        raise Http404
    return account.exchange


@session_api_required
@never_cache
@require_http_methods(["GET", "POST"])
def api_favorites(request):
    try:
        body = {}
        if request.method == "POST":
            if request.content_type != "application/json" or len(request.body) > 16000:
                raise ValidationError("JSON معتبر لازم است.")
            body = json.loads(request.body)
            if not isinstance(body, dict):
                raise ValidationError("JSON باید object باشد.")
        code = body.get("exchange") or request.GET.get("exchange")
        if not code:
            from apps.core.react_views import api_legacy_favorites

            return api_legacy_favorites(request)
        exchange = owned_exchange(request.user, code)
        if request.method == "POST":
            symbols = body.get("symbols")
            if not isinstance(symbols, list) or len(symbols) > 30:
                raise ValidationError("حداکثر ۳۰ ارز منتخب مجاز است.")
            symbols = list(dict.fromkeys(str(s).strip().upper() for s in symbols))
            if any(not re.fullmatch(r"[A-Z0-9]{2,20}", s) for s in symbols):
                raise ValidationError("نماد ارز معتبر نیست.")
            available = set(
                ExchangeMarket.objects.filter(
                    exchange=exchange,
                    active=True,
                    quote_asset__symbol="USDT",
                    base_asset__symbol__in=symbols,
                ).values_list("base_asset__symbol", flat=True)
            )
            if set(symbols) - available:
                raise ValidationError("ارز منتخب باید در بازار فعال همین صرافی باشد.")
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=request.user.pk)
                ExchangeFavorite.objects.filter(owner=request.user, exchange=exchange).delete()
                ExchangeFavorite.objects.bulk_create(
                    [
                        ExchangeFavorite(
                            owner=request.user, exchange=exchange, symbol=s, position=i
                        )
                        for i, s in enumerate(symbols)
                    ]
                )
        symbols = list(
            ExchangeFavorite.objects.filter(owner=request.user, exchange=exchange)
            .order_by("position", "pk")
            .values_list("symbol", flat=True)
        )
        return JsonResponse({"exchange": exchange.code, "symbols": symbols})
    except (ValidationError, ValueError, TypeError) as error:
        return JsonResponse({"error": getattr(error, "messages", [str(error)])}, status=400)


@session_api_required
@never_cache
@require_GET
def api_account_markets(request, pk):
    account = get_object_or_404(
        UserExchangeAccount.objects.for_user(request.user).select_related("exchange"),
        pk=pk,
        status__in=("connected", "restricted"),
        permissions__can_read=True,
    )
    try:
        offset = int(request.GET.get("offset", 0))
        limit = int(request.GET.get("limit", 100))
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError
    except ValueError:
        return JsonResponse({"error": ["صفحه یا تعداد نتایج معتبر نیست."]}, status=400)
    rows = ExchangeMarket.objects.filter(
        exchange=account.exchange,
        active=True,
        quote_asset__symbol="USDT",
        market_type__in=("spot", "margin"),
    ).select_related("base_asset", "quote_asset")
    q = request.GET.get("q", "").strip().upper()[:48]
    if q:
        rows = rows.filter(Q(base_asset__symbol__icontains=q) | Q(symbol__icontains=q))
    if request.GET.get("market_id"):
        try:
            rows = rows.filter(pk=int(request.GET["market_id"]))
        except ValueError:
            return JsonResponse({"error": ["شناسه بازار معتبر نیست."]}, status=400)
    favorites = list(
        ExchangeFavorite.objects.filter(owner=request.user, exchange=account.exchange)
        .order_by("position", "pk")
        .values_list("symbol", flat=True)
    )
    rows = rows.annotate(
        priority=Case(
            *[When(base_asset__symbol=symbol, then=Value(i)) for i, symbol in enumerate(favorites)],
            default=Value(9999),
            output_field=IntegerField(),
        )
    ).order_by("priority", "base_asset__symbol", "market_type", "pk")
    total = rows.count()
    page = list(rows[offset : offset + limit])
    next_offset = offset + len(page) if offset + len(page) < total else None
    return JsonResponse(
        {
            "account": {
                "id": account.pk,
                "exchange": account.exchange.code,
                "label": account.label,
            },
            "markets": [
                {
                    "id": m.pk,
                    "base": m.base_asset.symbol,
                    "symbol": m.symbol,
                    "market_type": m.market_type,
                    "max_leverage": str(m.max_leverage),
                    "price_step": str(m.price_step) if m.price_step else None,
                    "amount_step": str(m.amount_step) if m.amount_step else None,
                    "min_notional": str(m.min_notional) if m.min_notional else None,
                    "favorite": m.base_asset.symbol in favorites,
                }
                for m in page
            ],
            "total": total,
            "offset": offset,
            "next_offset": next_offset,
        }
    )
