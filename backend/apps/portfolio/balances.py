"""Balance valuation by account/wallet; never add unlike units or unknown liabilities."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.exchanges.models import BalanceSnapshot, ExchangeMarket
from apps.trading.models import CapitalReservation, OrderFill, PaperExitFill

from .quotes import quotes_for

ZERO = Decimal(0)


def balances_for(accounts, base_currency):
    accounts = list(accounts)
    ids = [a.pk for a in accounts]
    latest = list(
        BalanceSnapshot.objects.filter(exchange_account_id__in=ids)
        .select_related("asset")
        .order_by("exchange_account_id", "asset_id", "wallet_scope", "-captured_at", "-pk")
        .distinct("exchange_account_id", "asset_id", "wallet_scope")
    )
    markets = list(
        ExchangeMarket.objects.filter(
            exchange_id__in={a.exchange_id for a in accounts}, active=True, market_type="spot"
        ).select_related("base_asset", "quote_asset")
    )
    quotes, cache_ok = quotes_for(markets)
    rates = {}
    for market in markets:
        quote = quotes.get(market.pk)
        if not quote:
            continue
        if market.quote_asset.symbol == base_currency:
            rates[(market.exchange_id, market.base_asset.symbol)] = quote
        elif market.base_asset.symbol == base_currency:
            rates[(market.exchange_id, market.quote_asset.symbol)] = {
                **quote,
                "price": 1 / quote["price"],
            }
    paper_ids = [
        a.pk
        for a in accounts
        if a.environment == "paper" and a.exchange.adapter_code == "simulator"
    ]
    deltas = {}

    def add(account_id, symbol, amount):
        key = (account_id, symbol)
        deltas[key] = deltas.get(key, ZERO) + amount

    entries = OrderFill.objects.filter(account_id__in=paper_ids).select_related(
        "order__trade__market__base_asset", "order__trade__market__quote_asset"
    )
    for fill in entries:
        market = fill.order.trade.market
        add(fill.account_id, market.base_asset.symbol, fill.quantity)
        add(fill.account_id, market.quote_asset.symbol, -(fill.quantity * fill.price + fill.fee))
    for fill in PaperExitFill.objects.filter(trade__account_id__in=paper_ids).select_related(
        "trade__market__base_asset", "trade__market__quote_asset"
    ):
        add(fill.trade.account_id, fill.trade.market.base_asset.symbol, -fill.quantity)
        add(
            fill.trade.account_id,
            fill.trade.market.quote_asset.symbol,
            fill.quantity * fill.price - fill.fee,
        )
    reserved = {
        (r["account_id"], r["quote_asset__symbol"]): r["n"]
        for r in CapitalReservation.objects.filter(
            account_id__in=paper_ids, active=True, spent=False
        )
        .values("account_id", "quote_asset__symbol")
        .annotate(n=Sum("amount"))
    }
    groups = {
        a.pk: {
            "account": a,
            "rows": [],
            "valuation": ZERO,
            "available_valuation": ZERO,
            "complete": True,
            "base_currency": base_currency,
            "unknown": 0,
        }
        for a in accounts
    }
    seen = set()
    for snapshot in latest:
        account_id, symbol = snapshot.exchange_account_id, snapshot.asset.symbol
        group = groups[account_id]
        seen.add((account_id, symbol))
        free = snapshot.free_balance
        locked = snapshot.locked_balance
        if snapshot.wallet_scope == "spot":
            free += deltas.get((account_id, symbol), ZERO)
            reserve = reserved.get((account_id, symbol), ZERO)
        else:
            reserve = ZERO
        available = max(ZERO, free - reserve)
        rate = (
            {"price": Decimal(1), "observed_at": snapshot.captured_at, "source": "identity"}
            if symbol == base_currency
            else rates.get((group["account"].exchange_id, symbol))
        )
        stale = snapshot.captured_at < timezone.now() - timedelta(minutes=15)
        known = rate is not None and not stale and snapshot.wallet_scope == "spot" and free >= 0
        value = (free + locked) * rate["price"] if known else None
        group["rows"].append(
            {
                "asset": symbol,
                "wallet": snapshot.wallet_scope,
                "total": free + locked,
                "free": free,
                "locked": locked,
                "reserved": reserve,
                "available": available,
                "captured_at": snapshot.captured_at,
                "stale": stale,
                "rate": rate,
                "value": value,
            }
        )
        if known:
            group["valuation"] += value
            group["available_valuation"] += available * rate["price"]
        else:
            group["complete"], group["unknown"] = False, group["unknown"] + 1
    for (account_id, symbol), delta in deltas.items():
        if (account_id, symbol) not in seen and delta:
            groups[account_id]["complete"] = False
            groups[account_id]["unknown"] += 1
    for group in groups.values():
        if not group["rows"]:
            group["complete"] = False
    return list(groups.values()), cache_ok
