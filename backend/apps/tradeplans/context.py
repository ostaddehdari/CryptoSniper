"""Authenticated, owner-scoped input context; market prices are display-only."""

import json
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

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



@session_api_required
@never_cache
@require_GET
def account_markets(request):
    try:
        account_id = int(request.GET.get("account", ""))
    except (TypeError, ValueError):
        return JsonResponse({"error": "شناسه حساب لازم است."}, status=400)
    account = (
        UserExchangeAccount.objects.for_user(request.user)
        .filter(
            pk=account_id,
            environment="live",
            status__in=("connected", "restricted"),
            permissions__can_read=True,
        )
        .select_related("exchange")
        .first()
    )
    if account is None:
        return JsonResponse({"error": "حساب اصلی متصل پیدا نشد."}, status=404)
    rows = (
        ExchangeMarket.objects.filter(
            exchange=account.exchange,
            active=True,
            quote_asset__symbol="USDT",
            market_type__in=("spot", "margin"),
        )
        .select_related("base_asset", "quote_asset")
        .order_by("base_asset__symbol", "market_type")
    )
    items = []
    for market in rows:
        quote = get_quote(market)
        items.append(
            {
                "id": market.pk,
                "symbol": market.symbol,
                "asset": market.base_asset.symbol,
                "market_type": market.market_type,
                "max_leverage": str(market.max_leverage),
                "price": quote["price"] if quote and not quote["stale"] else None,
                "price_observed_at": quote["observed_at"] if quote else None,
                "price_stale": quote is None or quote["stale"],
                "price_step": str(market.price_step) if market.price_step else None,
                "amount_step": str(market.amount_step) if market.amount_step else None,
                "min_notional": str(market.min_notional) if market.min_notional else None,
            }
        )
    return JsonResponse(
        {
            "account": {"id": account.pk, "exchange": account.exchange.name, "label": account.label},
            "markets": items,
        }
    )


def _decimal(value, label):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{label} نامعتبر است.") from error
    if not number.is_finite() or number <= 0:
        raise ValueError(f"{label} باید بیشتر از صفر باشد.")
    return number


@session_api_required
@never_cache
@require_POST
def fix_loss(request):
    try:
        if request.content_type != "application/json":
            return JsonResponse({"error": "application/json لازم است."}, status=415)
        body = json.loads(request.body)
        account_id = int(body.get("account_id"))
        market_id = int(body.get("market_id"))
        entry = _decimal(body.get("entry"), "Entry")
        stop = _decimal(body.get("stop_loss"), "Stop Loss")
        risk_percent = _decimal(body.get("risk_percent"), "درصد ریسک")
        if risk_percent > Decimal("25"):
            raise ValueError("درصد ریسک برای محاسبه باید حداکثر ۲۵ باشد.")
        account = (
            UserExchangeAccount.objects.for_user(request.user)
            .filter(
                pk=account_id,
                environment="live",
                status__in=("connected", "restricted"),
                permissions__can_read=True,
            )
            .select_related("exchange")
            .first()
        )
        if account is None:
            return JsonResponse({"error": "حساب اصلی مجاز پیدا نشد."}, status=404)
        market = (
            ExchangeMarket.objects.filter(
                pk=market_id,
                exchange=account.exchange,
                active=True,
                quote_asset__symbol="USDT",
            )
            .select_related("quote_asset")
            .first()
        )
        if market is None:
            return JsonResponse({"error": "بازار USDT این حساب پیدا نشد."}, status=404)
        side = str(body.get("side", "long"))
        if side == "long" and stop >= entry:
            raise ValueError("برای Long حد ضرر باید پایین‌تر از Entry باشد.")
        if side == "short" and stop <= entry:
            raise ValueError("برای Short حد ضرر باید بالاتر از Entry باشد.")
        leverage = _decimal(body.get("leverage", 1), "اهرم")
        leverage = min(leverage, market.max_leverage)
        balance = (
            BalanceSnapshot.objects.filter(
                exchange_account=account,
                asset=market.quote_asset,
                wallet_scope="spot",
            )
            .order_by("-captured_at")
            .first()
        )
        free = balance.free_balance if balance else Decimal("0")
        stop_fraction = abs(entry - stop) / entry
        risk_amount = free * risk_percent / Decimal("100")
        raw_notional = risk_amount / stop_fraction
        max_notional = free * leverage
        suggested_notional = min(raw_notional, max_notional)
        required_collateral = suggested_notional / leverage
        below_minimum = bool(
            market.min_notional is not None and suggested_notional < market.min_notional
        )
        return JsonResponse(
            {
                "free_balance": free,
                "risk_percent": risk_percent,
                "risk_amount": risk_amount,
                "stop_distance_percent": stop_fraction * Decimal("100"),
                "requested_leverage": str(body.get("leverage", 1)),
                "used_leverage": leverage,
                "raw_notional": raw_notional,
                "suggested_notional": suggested_notional,
                "required_collateral": required_collateral,
                "capped_by_available_balance": suggested_notional < raw_notional,
                "below_min_notional": below_minimum,
                "min_notional": market.min_notional,
                "calculation_only": True,
            }
        )
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        return JsonResponse({"error": str(error)}, status=400)
