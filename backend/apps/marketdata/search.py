"""Owner-scoped market discovery. No cross-account market visibility."""

import re
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.exchanges.models import ExchangeMarket, UserExchangeAccount

SEARCH_TERM = re.compile(r"^[A-Z0-9/_-]{0,48}$")


def eligible_markets(user):
    if not user.is_authenticated:
        return ExchangeMarket.objects.none()
    # A provider can be read-only; that permits watching prices but never trading.
    readable_ids = []
    for account in (
        UserExchangeAccount.objects.for_user(user)
        .select_related("exchange")
        .filter(
            status__in=(UserExchangeAccount.Status.CONNECTED, UserExchangeAccount.Status.RESTRICTED)
        )
    ):
        if account.permissions.get("can_read") is True:
            readable_ids.append(account.exchange_id)
    return (
        ExchangeMarket.objects.filter(exchange_id__in=readable_ids, active=True)
        .select_related("exchange", "base_asset", "quote_asset")
        .order_by("exchange__code", "symbol", "market_type")
    )


def market_is_readable(user, market):
    return eligible_markets(user).filter(pk=market.pk).exists()


def search_markets(user, search="", limit=30):
    term = str(search).strip().upper()
    if not SEARCH_TERM.fullmatch(term):
        return []
    queryset = eligible_markets(user)
    if term:
        queryset = queryset.filter(
            Q(symbol__icontains=term)
            | Q(base_asset__symbol__istartswith=term)
            | Q(quote_asset__symbol__istartswith=term)
            | Q(exchange__name__icontains=term)
        )
    now = timezone.now()
    results = []
    for market in queryset[: max(1, min(int(limit), 50))]:
        metadata_fresh = bool(market.synced_at and now - market.synced_at <= timedelta(days=2))
        results.append(
            {
                "id": market.pk,
                "symbol": market.symbol,
                "exchange": market.exchange.code,
                "exchange_name": market.exchange.name,
                "market_type": market.market_type,
                "base_asset": market.base_asset.symbol,
                "quote_asset": market.quote_asset.symbol,
                "price_step": str(market.price_step) if market.price_step is not None else None,
                "amount_step": str(market.amount_step) if market.amount_step is not None else None,
                "min_notional": str(market.min_notional)
                if market.min_notional is not None
                else None,
                "metadata_fresh": metadata_fresh,
                "synced_at": market.synced_at.isoformat() if market.synced_at else None,
            }
        )
    return results
