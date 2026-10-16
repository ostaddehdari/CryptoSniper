"""Authenticated, owner-scoped input context; market prices are display-only."""

from decimal import Decimal

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.security import session_api_required
from apps.exchanges.models import BalanceSnapshot, ExchangeMarket, UserExchangeAccount
from apps.marketdata.feeds import get_quote


@session_api_required
@never_cache
@require_GET
def manual_context(request):
    try:
        account_id, market_id = (
            int(request.GET.get("account", "")),
            int(request.GET.get("market", "")),
        )
    except (TypeError, ValueError):
        return JsonResponse({"error": "شناسه حساب و بازار لازم است."}, status=400)
    account = (
        UserExchangeAccount.objects.for_user(request.user)
        .filter(pk=account_id, status__in=("connected", "restricted"), permissions__can_read=True)
        .select_related("exchange")
        .first()
    )
    if account is None:
        return JsonResponse({"error": "حساب مجاز پیدا نشد."}, status=404)
    market = (
        ExchangeMarket.objects.filter(pk=market_id, exchange=account.exchange, active=True)
        .select_related("quote_asset")
        .first()
    )
    if market is None:
        return JsonResponse({"error": "بازار حساب مجاز نیست."}, status=404)
    quote = get_quote(market)
    balance = (
        BalanceSnapshot.objects.filter(exchange_account=account, asset=market.quote_asset)
        .order_by("-captured_at")
        .first()
    )
    current_price = Decimal(quote["price"]) if quote and not quote["stale"] else None
    entry = request.GET.get("entry", "")
    distances = {}
    if current_price is not None:
        try:
            requested_entry = Decimal(entry)
            if requested_entry > 0 and requested_entry.is_finite():
                distances["price_to_entry_percent"] = str(
                    ((current_price - requested_entry) / requested_entry) * Decimal("100")
                )
        except (TypeError, ValueError, ArithmeticError):
            pass
    return JsonResponse(
        {
            "account": {
                "id": account.pk,
                "exchange": account.exchange.name,
                "status": account.status,
            },
            "market": {
                "id": market.pk,
                "symbol": market.symbol,
                "market_type": market.market_type,
                "tick_size": str(market.price_step) if market.price_step else None,
                "lot_step": str(market.amount_step) if market.amount_step else None,
                "max_leverage": str(market.max_leverage),
            },
            "quote": quote,
            "price_stale": quote is None or quote["stale"],
            "balance": (
                {
                    "free": str(balance.free_balance),
                    "asset": market.quote_asset.symbol,
                    "captured_at": balance.captured_at.isoformat(),
                }
                if balance
                else None
            ),
            "distances": distances,
            "execution_enabled": False,
        }
    )
