import asyncio
import json
import re
import uuid
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.audit import record_audit
from apps.accounts.models import UserSession, WalletConnection
from apps.accounts.security import has_recent_step_up, mark_step_up, session_api_required
from apps.accounts.retention import retained_audit_events
from apps.accounts.services import revoke_user_session
from apps.alerts.models import Notification, NotificationPreference
from apps.exchanges.forms import ExchangeConnectionForm, LiveSpotOrderForm
from apps.exchanges.live_orders import queue_live_spot_order
from apps.exchanges.models import BalanceSnapshot, Exchange, ExchangeMarket, LiveSpotOrder, UserExchangeAccount
from apps.exchanges.security import revoke_account_credentials, rotate_account_credentials
from apps.exchanges.services import latest_balances
from apps.exchanges.tasks import live_spot_order, sync_exchange_account
from apps.marketdata.feeds import get_quote
from apps.marketdata.search import market_is_readable
from apps.marketdata.models import FavoriteAsset, HistoricalCandle, Watchlist, WatchlistItem
from apps.operations.models import ExternalObservation, WorkerHeartbeat
from apps.operations.tasks import reconcile_one
from apps.portfolio.balances import balances_for
from apps.signals.backfill import pause_backfill, process_backfill_batch, start_backfill
from apps.signals.models import Signal, SignalSource, TelegramAccount, TelegramBackfillJob, TelegramChannel, TelegramMessage
from apps.signals.telegram_client import available_channels, complete_login, configure_channel, request_login_code
from apps.signals.telegram_security import revoke_telegram_credentials
from apps.tradeplans.models import TradePlan
from apps.tradeplans.service import approve_plan


SAFE_SYMBOL = re.compile(r"^[A-Z0-9]{2,20}$")


def _body(request):
    if request.content_type != "application/json":
        raise ValidationError("application/json لازم است.")
    if len(request.body) > 256000:
        raise ValidationError("درخواست بیش از حد بزرگ است.")
    try:
        value = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError) as error:
        raise ValidationError("JSON نامعتبر است.") from error
    if not isinstance(value, dict):
        raise ValidationError("JSON باید object باشد.")
    forbidden = {"private_key", "privateKey", "seed", "seed_phrase", "seedPhrase", "mnemonic"}
    if forbidden & set(value):
        raise ValidationError("Seed Phrase و Private Key قابل ثبت نیست.")
    return value




def legacy_react_page(request, page="dashboard", **kwargs):
    """Keep old bookmarks working while the React workspace becomes the primary UI."""
    return redirect(f"{reverse('react-app')}#/{page}")


def paper_mode_removed(request, **kwargs):
    """Paper/Demo HTTP surface is retired; legacy data remains read-only in the database."""
    if request.method == "GET":
        return legacy_react_page(request, page="trades")
    return JsonResponse({"error": "paper_mode_removed", "redirect": f"{reverse('react-app')}#/trades"}, status=410)


@login_required
@never_cache
@require_GET
def react_app(request):
    return render(request, "react_app.html", {"release": "stage27-trading-workflow"})


def _balance_payload(account):
    rows = latest_balances(account)
    rows.sort(key=lambda x: (0 if x.asset.symbol == "USDT" else 1, x.asset.symbol))
    return [
        {
            "asset": row.asset.symbol,
            "free": str(row.free_balance),
            "locked": str(row.locked_balance),
            "total": str(row.total_balance),
            "usd_value": str(row.usd_value) if row.usd_value is not None else None,
            "captured_at": row.captured_at.isoformat(),
        }
        for row in rows
    ]




@session_api_required
@require_POST
def api_step_up(request):
    try:
        data = _body(request)
        if not request.user.check_password(str(data.get("password", ""))):
            record_audit("auth.step_up_failed", request=request, user=request.user)
            return JsonResponse({"error": "invalid_password"}, status=403)
        mark_step_up(request)
        record_audit("auth.step_up_succeeded", request=request, user=request.user)
        return JsonResponse({"verified": True, "valid_minutes": 10})
    except ValidationError as error:
        return JsonResponse({"error": error.messages}, status=400)


@session_api_required
@never_cache
@require_GET
def api_bootstrap(request):
    accounts = list(
        UserExchangeAccount.objects.for_user(request.user)
        .select_related("exchange")
        .exclude(exchange__code="binance")
        .exclude(status="disabled")
    )
    valuation_rows, valuation_cache_ok = balances_for(accounts, request.user.base_currency)
    valuations = {row["account"].pk: row for row in valuation_rows}
    unread = Notification.objects.filter(owner=request.user, in_app=True, read_at__isnull=True).count()
    favorite_rows = list(
        FavoriteAsset.objects.filter(owner=request.user, exchange__isnull=False)
        .select_related("exchange")
        .order_by("exchange_id", "position", "pk")
    )
    favorites = {}
    for item in favorite_rows:
        favorites.setdefault(item.exchange.code, []).append(item.symbol)
    watchlists = list(Watchlist.objects.filter(owner=request.user).values("id", "name"))
    return JsonResponse(
        {
            "user": {
                "id": request.user.pk,
                "name": request.user.preferred_name,
                "base_currency": request.user.base_currency,
                "timezone": request.user.timezone,
            },
            "dashboard": {
                "open_orders": LiveSpotOrder.objects.filter(owner=request.user, state__in=("pending", "submitting", "open", "partial")).count(),
                "active_signals": Signal.objects.filter(owner=request.user, status__in=("new", "parsed", "needs_review", "approved")).count(),
            },
            "accounts": [
                {
                    "id": a.pk,
                    "exchange": a.exchange.code,
                    "exchange_name": a.exchange.name,
                    "label": a.label,
                    "status": a.status,
                    "environment": a.environment,
                    "trading_enabled": a.trading_enabled,
                    "permissions": a.permissions,
                    "last_verified_at": a.last_verified_at,
                    "last_sync_at": a.last_sync_at,
                    "last_error_code": a.last_error_code,
                    "last_error_message": a.last_error_message,
                    "known_valuation": str(valuations[a.pk]["valuation"])
                    if a.pk in valuations
                    else None,
                    "known_available_valuation": str(
                        valuations[a.pk]["available_valuation"]
                    )
                    if a.pk in valuations
                    else None,
                    "valuation_complete": bool(valuations[a.pk]["complete"])
                    if a.pk in valuations
                    else False,
                    "unvalued_assets": valuations[a.pk]["unknown"]
                    if a.pk in valuations
                    else 0,
                    "balances": _balance_payload(a),
                }
                for a in accounts
                if a.environment == "live" and a.exchange.adapter_code != "simulator"
            ],
            "unread_notifications": unread,
            "valuation_cache_ok": valuation_cache_ok,
            "favorites": favorites,
            "watchlists": watchlists,
        }
    )




@session_api_required
@never_cache
@require_http_methods(["GET", "POST"])
def api_watchlists_ui(request):
    if request.method == "GET":
        lists = list(Watchlist.objects.filter(owner=request.user))
        if not lists:
            lists = [Watchlist.objects.create(owner=request.user, name="منتخب من")]
        return JsonResponse({
            "watchlists": [
                {
                    "id": wl.pk,
                    "name": wl.name,
                    "items": [
                        {
                            "id": item.pk,
                            "market_id": item.market_id,
                            "symbol": item.market.symbol,
                            "base": item.market.base_asset.symbol,
                            "exchange": item.market.exchange.code,
                            "market_type": item.market.market_type,
                            "max_leverage": str(item.market.max_leverage),
                            "quote": get_quote(item.market),
                        }
                        for item in wl.items.select_related(
                            "market", "market__exchange", "market__base_asset"
                        )[:100]
                        if market_is_readable(request.user, item.market)
                    ],
                }
                for wl in lists
            ]
        })
    try:
        data = _body(request)
        action = str(data.get("action", ""))
        if action == "create":
            name = str(data.get("name", "")).strip()
            if not 1 <= len(name) <= 64:
                raise ValidationError("نام فهرست معتبر نیست.")
            wl, created = Watchlist.objects.get_or_create(owner=request.user, name=name)
            return JsonResponse({"id": wl.pk, "created": created}, status=201 if created else 200)
        wl = get_object_or_404(Watchlist, owner=request.user, pk=int(data.get("watchlist_id")))
        if action == "add":
            market = get_object_or_404(ExchangeMarket, pk=int(data.get("market_id")))
            if not market_is_readable(request.user, market):
                raise ValidationError("برای این بازار اتصال خواندنی ندارید.")
            item, created = WatchlistItem.objects.get_or_create(watchlist=wl, market=market)
            return JsonResponse({"id": item.pk, "created": created}, status=201 if created else 200)
        if action == "remove":
            deleted, _ = WatchlistItem.objects.filter(watchlist=wl, pk=int(data.get("item_id"))).delete()
            return JsonResponse({"deleted": bool(deleted)})
        raise ValidationError("عملیات فهرست معتبر نیست.")
    except (ValidationError, ValueError, TypeError) as error:
        return JsonResponse({"error": getattr(error, "messages", [str(error)])}, status=400)


@session_api_required
@never_cache
@require_http_methods(["GET", "POST"])
def api_favorites(request):
    if request.method == "GET":
        rows = (
            FavoriteAsset.objects.filter(owner=request.user, exchange__isnull=False)
            .select_related("exchange")
            .order_by("exchange_id", "position", "pk")
        )
        grouped = {}
        for item in rows:
            grouped.setdefault(item.exchange.code, []).append(item.symbol)
        return JsonResponse({"by_exchange": grouped})
    try:
        data = _body(request)
        exchange_code = str(data.get("exchange", "")).strip().lower()
        account = (
            UserExchangeAccount.objects.for_user(request.user)
            .select_related("exchange")
            .filter(environment="live", exchange__code=exchange_code)
            .exclude(status="disabled")
            .first()
        )
        if not account:
            raise ValidationError("صرافی متصل معتبر نیست.")
        symbols = data.get("symbols", [])
        if not isinstance(symbols, list) or len(symbols) > 40:
            raise ValidationError("حداکثر ۴۰ ارز منتخب برای هر صرافی مجاز است.")
        normalized = []
        for raw in symbols:
            symbol = str(raw).strip().upper()
            if not SAFE_SYMBOL.fullmatch(symbol):
                raise ValidationError(f"نماد نامعتبر: {symbol}")
            if symbol not in normalized:
                normalized.append(symbol)
        valid_symbols = set(
            ExchangeMarket.objects.filter(
                exchange=account.exchange,
                active=True,
                quote_asset__symbol="USDT",
                base_asset__symbol__in=normalized,
            ).values_list("base_asset__symbol", flat=True)
        )
        missing = [symbol for symbol in normalized if symbol not in valid_symbols]
        if missing:
            raise ValidationError(
                "این ارزها در بازار فعال صرافی پیدا نشدند: " + ", ".join(missing[:10])
            )
        with transaction.atomic():
            FavoriteAsset.objects.filter(
                owner=request.user, exchange=account.exchange
            ).delete()
            FavoriteAsset.objects.bulk_create(
                [
                    FavoriteAsset(
                        owner=request.user,
                        exchange=account.exchange,
                        symbol=symbol,
                        position=index,
                    )
                    for index, symbol in enumerate(normalized)
                ]
            )
        return JsonResponse({"exchange": account.exchange.code, "symbols": normalized})
    except ValidationError as error:
        return JsonResponse({"error": error.messages}, status=400)


@session_api_required
@never_cache
@require_http_methods(["GET", "POST"])
def api_wallets(request):
    if request.method == "GET":
        rows = WalletConnection.objects.for_user(request.user).exclude(status="disabled")
        return JsonResponse(
            {
                "wallets": [
                    {
                        "id": item.pk,
                        "provider": item.provider,
                        "provider_label": item.get_provider_display(),
                        "network": item.network,
                        "label": item.label,
                        "address": item.address,
                        "status": item.status,
                        "verified_at": item.verified_at,
                    }
                    for item in rows
                ]
            }
        )
    try:
        data = _body(request)
        provider = str(data.get("provider", "")).strip()
        valid = {value for value, _ in WalletConnection.Provider.choices}
        if provider not in valid:
            raise ValidationError("نوع کیف پول معتبر نیست.")
        address = str(data.get("address", "")).strip()
        if not address or len(address) > 160:
            raise ValidationError("آدرس عمومی کیف پول معتبر نیست.")
        label = str(data.get("label", "")).strip()[:80] or dict(WalletConnection.Provider.choices).get(provider, provider)
        network = str(data.get("network", "ethereum")).strip().lower()[:40]
        status = str(data.get("status", "watch_only"))
        if status not in {"watch_only", "connected"}:
            status = "watch_only"
        item, created = WalletConnection.objects.update_or_create(
            owner=request.user,
            provider=provider,
            network=network,
            address=address,
            defaults={"label": label, "status": status, "metadata": {"source": "react-ui"}},
        )
        return JsonResponse({"id": item.pk, "created": created}, status=201 if created else 200)
    except ValidationError as error:
        return JsonResponse({"error": error.messages}, status=400)


@session_api_required
@require_http_methods(["DELETE"])
def api_wallet_detail(request, pk):
    item = get_object_or_404(WalletConnection.objects.for_user(request.user), pk=pk)
    item.status = WalletConnection.Status.DISABLED
    item.save(update_fields=("status", "updated_at"))
    return JsonResponse({"deleted": True})




@session_api_required
@never_cache
@require_POST
def api_exchange_create(request):
    try:
        data = _body(request)
        exchange_value = data.get("exchange")
        exchange = None
        if isinstance(exchange_value, str) and not exchange_value.isdigit():
            exchange = get_object_or_404(
                Exchange,
                code=exchange_value.strip().lower(),
                enabled=True,
            )
        else:
            exchange = get_object_or_404(
                Exchange,
                pk=int(exchange_value),
                enabled=True,
            )
        form = ExchangeConnectionForm(
            request.user,
            {
                "exchange": exchange.pk,
                "label": data.get("label") or "حساب اصلی",
                "environment": "live",
                "api_key": data.get("api_key", ""),
                "api_secret": data.get("api_secret", ""),
                "passphrase": data.get("passphrase", ""),
                "no_withdrawal_confirmed": "on" if data.get("no_withdrawal_confirmed") is True else "",
                "ip_restricted_confirmed": "on" if data.get("ip_restricted_confirmed") is True else "",
            },
        )
        form.fields["exchange"].queryset = form.fields["exchange"].queryset.exclude(
            Q(adapter_code="simulator") | Q(code="binance")
        )
        if not form.is_valid():
            return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
        account = form.save()
        sync_exchange_account.apply_async(args=[account.pk], queue="maintenance")
        return JsonResponse({"id": account.pk, "status": account.status}, status=201)
    except ValidationError as error:
        return JsonResponse({"error": error.messages}, status=400)


@session_api_required
@never_cache
@require_GET
def api_account_markets(request, pk):
    account = get_object_or_404(
        UserExchangeAccount.objects.for_user(request.user).select_related("exchange"),
        pk=pk,
        environment="live",
    )
    favorites = list(
        FavoriteAsset.objects.filter(owner=request.user, exchange=account.exchange)
        .order_by("position", "pk")
        .values_list("symbol", flat=True)
    )
    favorite_position = {symbol: index for index, symbol in enumerate(favorites)}
    markets = list(
        ExchangeMarket.objects.filter(
            exchange=account.exchange,
            active=True,
            quote_asset__symbol="USDT",
        )
        .select_related("base_asset", "quote_asset")
        .order_by("base_asset__symbol", "market_type")[:1000]
    )
    markets.sort(
        key=lambda item: (
            0 if item.base_asset.symbol in favorite_position else 1,
            favorite_position.get(item.base_asset.symbol, 9999),
            item.base_asset.symbol,
            item.market_type,
        )
    )
    return JsonResponse(
        {
            "account": {"id": account.pk, "exchange": account.exchange.code, "label": account.label},
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
                    "favorite": m.base_asset.symbol in favorite_position,
                }
                for m in markets
            ],
        }
    )




@session_api_required
@never_cache
@require_GET
def api_market_candles(request, pk):
    market = get_object_or_404(ExchangeMarket.objects.select_related("exchange"), pk=pk, active=True)
    if not UserExchangeAccount.objects.for_user(request.user).filter(
        exchange=market.exchange, status__in=("connected", "restricted"), permissions__can_read=True
    ).exists():
        return JsonResponse({"error": "market_not_visible"}, status=404)
    interval = str(request.GET.get("interval", "1h"))
    if interval not in {"15m", "1h", "4h", "1d"}:
        interval = "1h"
    rows = list(
        HistoricalCandle.objects.filter(symbol=market.symbol, interval=interval)
        .order_by("-open_time")[:120]
    )
    rows.reverse()
    return JsonResponse({
        "market_id": market.pk,
        "symbol": market.symbol,
        "interval": interval,
        "candles": [
            {
                "time": row.open_time.isoformat(),
                "open": str(row.open_price),
                "high": str(row.high_price),
                "low": str(row.low_price),
                "close": str(row.close_price),
                "volume": str(row.volume),
            }
            for row in rows
        ],
    })


@session_api_required
@never_cache
@require_GET
def api_exchange_diagnostics(request, pk):
    account = get_object_or_404(
        UserExchangeAccount.objects.for_user(request.user).select_related("exchange"), pk=pk
    )
    heartbeats = {
        row.queue: {"seen_at": row.seen_at.isoformat(), "worker": row.worker, "lag_seconds": row.lag_seconds}
        for row in WorkerHeartbeat.objects.filter(queue__in=("maintenance", "orders", "market_data"))
    }
    return JsonResponse(
        {
            "account": {
                "id": account.pk,
                "exchange": account.exchange.code,
                "label": account.label,
                "status": account.status,
                "credential_hint": account.credential_hint,
                "permissions": account.permissions,
                "trading_enabled": account.trading_enabled,
                "last_verified_at": account.last_verified_at,
                "last_sync_at": account.last_sync_at,
                "last_error": {
                    "code": account.last_error_code,
                    "message": account.last_error_message,
                    "at": account.last_error_at,
                },
                "balances": _balance_payload(account),
            },
            "checks": {
                "credentials_present": bool(account.credentials_encrypted),
                "read_permission": account.permissions.get("can_read") is True,
                "trade_permission": bool(account.permissions.get("can_trade_spot") or account.permissions.get("can_trade_margin")),
                "withdrawal_disabled": account.permissions.get("can_withdraw") is False,
                "ip_restricted": account.permissions.get("ip_restricted"),
            },
            "workers": heartbeats,
        }
    )


@session_api_required
@require_POST
def api_exchange_sync(request, pk):
    account = get_object_or_404(UserExchangeAccount.objects.for_user(request.user), pk=pk)
    if account.status == "disabled":
        return JsonResponse({"error": "account_disabled"}, status=409)
    sync_exchange_account.apply_async(args=[account.pk], queue="maintenance")
    reconcile_one.apply_async(args=[account.pk], queue="maintenance", countdown=5)
    return JsonResponse({"queued": True, "account_id": account.pk}, status=202)


@session_api_required
@require_POST
def api_exchange_rotate(request, pk):
    if not has_recent_step_up(request):
        return JsonResponse({"error": "step_up_required", "verify_url": "/cryptosniper/settings/security/step-up/"}, status=403)
    account = get_object_or_404(UserExchangeAccount.objects.for_user(request.user), pk=pk)
    if account.status == "disabled" or not account.credentials_encrypted:
        return JsonResponse({"error": "account_disabled_or_missing_credentials"}, status=409)
    try:
        data = _body(request)
        if data.get("confirmed") is not True:
            raise ValidationError("تأیید گردش کلید رمزنگاری لازم است.")
        version = rotate_account_credentials(account)
        account.trading_enabled = False
        account.status = "pending"
        account.save(update_fields=("trading_enabled", "status", "updated_at"))
        record_audit(
            "exchange_account.credentials_rotated",
            request=request, user=request.user,
            metadata={"account_id": account.pk, "key_version": version},
        )
        sync_exchange_account.apply_async(args=[account.pk], queue="maintenance")
        return JsonResponse({"rotated": True, "key_version": version, "status": account.status})
    except ValidationError as error:
        return JsonResponse({"error": error.messages}, status=400)


@session_api_required
@require_POST
def api_exchange_revoke(request, pk):
    if not has_recent_step_up(request):
        return JsonResponse({"error": "step_up_required", "verify_url": "/cryptosniper/settings/security/step-up/"}, status=403)
    account = get_object_or_404(UserExchangeAccount.objects.for_user(request.user), pk=pk)
    try:
        data = _body(request)
        if data.get("confirmed") is not True:
            raise ValidationError("تأیید حذف اتصال لازم است.")
        revoke_account_credentials(account)
        account.status = "disabled"
        account.trading_enabled = False
        account.save(update_fields=("status", "trading_enabled", "updated_at"))
        return JsonResponse({"revoked": True})
    except ValidationError as error:
        return JsonResponse({"error": error.messages}, status=400)


@session_api_required
@never_cache
@require_POST
def api_fix_loss(request):
    try:
        data = _body(request)
        account = get_object_or_404(UserExchangeAccount.objects.for_user(request.user), pk=int(data.get("account_id")))
        market = get_object_or_404(ExchangeMarket, pk=int(data.get("market_id")), exchange=account.exchange, active=True)
        entry = Decimal(str(data.get("entry")))
        stop = Decimal(str(data.get("stop")))
        risk_percent = Decimal(str(data.get("risk_percent", "1")))
        leverage = Decimal(str(data.get("leverage", "1")))
        if entry <= 0 or stop <= 0 or entry == stop or not Decimal("0") < risk_percent <= Decimal("20"):
            raise ValidationError("ورودی Fix Loss معتبر نیست.")
        leverage = max(Decimal("1"), min(leverage, market.max_leverage or Decimal("1")))
        balance = (
            BalanceSnapshot.objects.filter(exchange_account=account, asset=market.quote_asset)
            .order_by("-captured_at")
            .first()
        )
        if not balance:
            raise ValidationError("موجودی آزاد Quote برای این حساب در دسترس نیست.")
        available = balance.free_balance
        risk_budget = available * risk_percent / Decimal("100")
        stop_fraction = abs(entry - stop) / entry
        raw_notional = risk_budget / stop_fraction
        max_notional = available * leverage
        suggested = min(raw_notional, max_notional)
        quantity = suggested / entry
        if market.amount_step:
            quantity = (quantity // market.amount_step) * market.amount_step
        if market.min_amount and quantity < market.min_amount:
            raise ValidationError("حجم محاسبه‌شده از حداقل مقدار بازار کمتر است.")
        suggested = quantity * entry
        if market.min_notional and suggested < market.min_notional:
            raise ValidationError("حجم محاسبه‌شده از حداقل ارزش سفارش بازار کمتر است.")
        return JsonResponse(
            {
                "available": str(available),
                "risk_budget": str(risk_budget),
                "stop_distance_percent": str(stop_fraction * Decimal("100")),
                "max_leverage": str(market.max_leverage),
                "used_leverage": str(leverage),
                "raw_notional": str(raw_notional),
                "suggested_notional": str(suggested),
                "suggested_quantity": str(quantity),
                "capped_by_available_balance": raw_notional > max_notional,
                "advisory_only": True,
            }
        )
    except (ValidationError, ValueError, TypeError, InvalidOperation) as error:
        return JsonResponse({"error": getattr(error, "messages", [str(error)])}, status=400)


def _live_order_payload(item):
    management = getattr(item, "managed_entry", None)
    if management is not None:
        from apps.operations.managed_live import serialize_management

        management_payload = serialize_management(management)
        order_role = "entry"
    elif hasattr(item, "managed_target_exit"):
        management_payload = None
        order_role = "managed_tp_exit"
    elif hasattr(item, "managed_full_exit"):
        management_payload = None
        order_role = "managed_stop_exit"
    else:
        management_payload = None
        order_role = "order"
    return {
        "id": item.pk,
        "source": "cryptosniper",
        "role": order_role,
        "exchange": item.account.exchange.code,
        "account": item.account.label,
        "symbol": item.market.symbol,
        "side": item.side,
        "order_type": item.order_type,
        "amount": str(item.amount),
        "price": str(item.price) if item.price is not None else None,
        "filled_amount": str(item.filled_amount),
        "average_price": str(item.average_price) if item.average_price is not None else None,
        "state": item.state,
        "error_code": item.error_code,
        "management": management_payload,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


@session_api_required
@never_cache
@require_http_methods(["GET", "POST"])
def api_live_orders(request):
    if request.method == "GET":
        internal = list(
            LiveSpotOrder.objects.filter(owner=request.user)
            .select_related("account", "account__exchange", "market")
            .order_by("-created_at")[:200]
        )
        external = list(
            ExternalObservation.objects.filter(account__owner=request.user, kind__in=("order", "fill"))
            .select_related("account", "account__exchange")
            .order_by("-observed_at")[:200]
        )
        from apps.operations.external_management import (
            normalize_external,
            serialize_management,
        )

        external_rows = []
        for item in external:
            row = normalize_external(item)
            row["source"] = "external"
            row["management"] = serialize_management(
                getattr(item, "management", None)
            )
            external_rows.append(row)
        return JsonResponse(
            {
                "orders": [_live_order_payload(item) for item in internal],
                "external": external_rows,
            }
        )

    if not has_recent_step_up(request):
        return JsonResponse({"error": "step_up_required", "verify_url": "/cryptosniper/settings/security/step-up/"}, status=403)
    try:
        data = _body(request)
        account = get_object_or_404(UserExchangeAccount.objects.for_user(request.user), pk=int(data.get("account")))
        form = LiveSpotOrderForm(
            request.user,
            account,
            {
                "market": data.get("market"),
                "side": data.get("side"),
                "amount": data.get("amount"),
                "price": data.get("price"),
                "request_key": data.get("request_key") or str(uuid.uuid4()),
                "confirmed": "on" if data.get("confirmed") is True else "",
            },
        )
        if not form.is_valid():
            return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
        plan_id = data.get("plan_id")
        plan_revision = data.get("plan_revision")
        with transaction.atomic():
            plan = None
            if plan_id not in {None, ""}:
                plan = approve_plan(
                    request.user,
                    int(plan_id),
                    int(plan_revision or 0),
                )
                if (
                    plan.exchange_account_id != account.pk
                    or plan.market_id != form.cleaned_data["market"].pk
                ):
                    raise ValidationError("برنامه معامله با حساب یا بازار سفارش هم‌خوان نیست.")
            order, created = queue_live_spot_order(
                request.user,
                account,
                form.cleaned_data,
            )
            if plan is not None:
                from apps.operations.managed_live import create_management

                create_management(request.user, plan.pk, order)
            if created:
                transaction.on_commit(
                    lambda order_id=order.pk: live_spot_order.apply_async(
                        args=[order_id],
                        queue="orders",
                    )
                )
        return JsonResponse(
            {"order": _live_order_payload(order), "created": created},
            status=201 if created else 200,
        )
    except (ValidationError, ValueError, TypeError) as error:
        return JsonResponse({"error": getattr(error, "messages", [str(error)])}, status=400)




@session_api_required
@never_cache
@require_GET
def api_manual_plans_ui(request):
    rows = (
        TradePlan.objects.filter(owner=request.user)
        .select_related("exchange_account", "exchange_account__exchange", "market")
        .order_by("-created_at")[:100]
    )
    return JsonResponse({
        "plans": [
            {
                "id": item.pk,
                "status": item.status,
                "revision": item.revision,
                "account_id": item.exchange_account_id,
                "account": item.exchange_account.label,
                "exchange": item.exchange_account.exchange.code,
                "market_id": item.market_id,
                "symbol": item.market.symbol,
                "market_type": item.market.market_type,
                "side": item.side,
                "entry": str(item.entry_price),
                "stop_loss": str(item.stop_loss),
                "tp1": str(item.tp1),
                "tp2": str(item.tp2) if item.tp2 is not None else None,
                "tp3": str(item.tp3) if item.tp3 is not None else None,
                "capital": str(item.capital),
                "leverage": str(item.leverage),
                "trailing_sl": item.trailing_sl,
                "percentage_trailing": item.percentage_trailing,
                "percentage_trigger": item.percentage_trigger,
                "trailing_distance": str(item.trailing_distance),
                "client_token": str(item.client_token),
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            for item in rows
        ]
    })


@session_api_required
@never_cache
@require_http_methods(["GET", "POST"])
def api_signal_sources_ui(request):
    for method, name in (
        (SignalSource.Method.MANUAL, "ورود دستی من"),
        (SignalSource.Method.SMART_PASTE, "Smart Paste من"),
    ):
        SignalSource.objects.get_or_create(owner=request.user, method=method, name=name)
    if request.method == "POST":
        try:
            data = _body(request)
            source = get_object_or_404(SignalSource, owner=request.user, pk=int(data.get("id")))
            if source.method == SignalSource.Method.TELEGRAM:
                raise ValidationError("کانال‌های Telegram از بخش Telegram مدیریت می‌شوند.")
            source.enabled = data.get("enabled") is True
            source.save(update_fields=("enabled",))
            record_audit(
                "signal_source.updated",
                request=request,
                user=request.user,
                metadata={"source_id": source.pk, "enabled": source.enabled},
            )
        except (ValidationError, ValueError, TypeError) as error:
            return JsonResponse({"error": getattr(error, "messages", [str(error)])}, status=400)
    rows = SignalSource.objects.filter(owner=request.user).order_by("method", "name", "pk")
    return JsonResponse({
        "sources": [
            {"id": row.pk, "name": row.name, "method": row.method, "enabled": row.enabled}
            for row in rows
        ]
    })


@session_api_required
@never_cache
@require_http_methods(["GET", "PATCH"])
def api_notification_preferences_ui(request):
    pref, _ = NotificationPreference.objects.get_or_create(owner=request.user)
    if request.method == "PATCH":
        try:
            data = _body(request)
            allowed = {"in_app", "browser"}
            if set(data) - allowed:
                raise ValidationError("فیلد تنظیم اعلان پشتیبانی نمی‌شود.")
            if "in_app" in data:
                pref.in_app = data["in_app"] is True
            if "browser" in data:
                pref.browser = data["browser"] is True
            pref.save(update_fields=("in_app", "browser"))
            record_audit(
                "notification_preferences.updated",
                request=request,
                user=request.user,
                metadata={"in_app": pref.in_app, "browser": pref.browser},
            )
        except ValidationError as error:
            return JsonResponse({"error": error.messages}, status=400)
    return JsonResponse({"preferences": {"in_app": pref.in_app, "browser": pref.browser}})


@session_api_required
@never_cache
@require_http_methods(["GET", "POST"])
def api_security_state_ui(request):
    if request.method == "POST":
        try:
            data = _body(request)
            if data.get("action") != "revoke_session":
                raise ValidationError("عملیات امنیتی پشتیبانی نمی‌شود.")
            item = get_object_or_404(UserSession.objects.for_user(request.user), pk=int(data.get("session_id")))
            current = item.session_key == request.session.session_key
            if current:
                raise ValidationError("نشست جاری را از دکمه خروج ببندید.")
            revoke_user_session(item, request=request)
            record_audit(
                "session.revoked_from_ui",
                request=request,
                user=request.user,
                metadata={"session_id": item.pk},
            )
        except (ValidationError, ValueError, TypeError) as error:
            return JsonResponse({"error": getattr(error, "messages", [str(error)])}, status=400)
    sessions = UserSession.objects.for_user(request.user).order_by("-last_seen_at")[:30]
    events = retained_audit_events(request.user)[:100]
    current_key = request.session.session_key
    return JsonResponse({
        "sessions": [
            {
                "id": item.pk,
                "label": item.user_agent_label,
                "created_at": item.created_at,
                "last_seen_at": item.last_seen_at,
                "expires_at": item.expires_at,
                "revoked_at": item.revoked_at,
                "current": item.session_key == current_key,
                "valid": item.is_currently_valid,
            }
            for item in sessions
        ],
        "audit": [
            {
                "id": item.pk,
                "event_type": item.event_type,
                "metadata": item.metadata,
                "created_at": item.created_at,
            }
            for item in events
        ],
    })


@session_api_required
@never_cache
@require_GET
def api_telegram_state(request):
    account, _ = TelegramAccount.objects.get_or_create(owner=request.user)
    channels = list(TelegramChannel.objects.filter(owner=request.user).select_related("source"))
    return JsonResponse(
        {
            "account": {
                "status": account.status,
                "label": account.label,
                "phone_hint": account.phone_hint,
                "last_error": account.last_error,
                "connected_at": account.connected_at,
            },
            "channels": [
                {
                    "id": c.pk,
                    "title": c.title,
                    "username": c.username,
                    "peer_id": c.peer_id,
                    "parse_mode": c.parse_mode,
                    "automation": c.automation,
                    "enabled": c.enabled,
                    "last_message_id": c.last_message_id,
                    "min_confidence": c.min_confidence,
                    "backfill": (
                        {
                            "id": job.pk,
                            "status": job.status,
                            "scanned": job.scanned_messages,
                            "imported": job.imported_messages,
                            "cursor": job.cursor_message_id,
                            "error": job.last_error,
                        }
                        if (job := c.backfill_jobs.order_by("-created_at").first())
                        else None
                    ),
                }
                for c in channels
            ],
            "discovered": request.session.get("telegram_discovered_channels", []),
        }
    )


@session_api_required
@never_cache
@require_GET
def api_telegram_messages(request):
    qs = TelegramMessage.objects.filter(owner=request.user).select_related("channel", "raw_signal")
    channel = request.GET.get("channel")
    if channel and channel.isdigit():
        qs = qs.filter(channel_id=int(channel))
    q = str(request.GET.get("q", "")).strip()
    if q:
        qs = qs.filter(raw_signal__original_text__icontains=q)
    kind = str(request.GET.get("kind", "")).strip()
    if kind:
        qs = qs.filter(message_kind=kind)
    rows = qs.order_by("-occurred_at", "-message_id")[:200]
    return JsonResponse(
        {
            "messages": [
                {
                    "id": item.pk,
                    "channel_id": item.channel_id,
                    "channel": item.channel.title,
                    "message_id": item.message_id,
                    "kind": item.message_kind,
                    "text": item.raw_signal.original_text if item.raw_signal_id else "",
                    "occurred_at": item.occurred_at,
                    "edited_at": item.edited_at,
                    "deleted": item.deleted_at is not None,
                }
                for item in rows
            ]
        }
    )


@session_api_required
@never_cache
@require_POST
def api_telegram_action(request):
    account, _ = TelegramAccount.objects.get_or_create(owner=request.user)
    try:
        data = _body(request)
        action = str(data.get("action", ""))
        if action in {"connect", "resend", "code", "revoke"} and not has_recent_step_up(request):
            return JsonResponse({"error": "step_up_required", "verify_url": "/cryptosniper/settings/security/step-up/"}, status=403)
        if action == "connect":
            asyncio.run(request_login_code(account, int(data["api_id"]), str(data["api_hash"]), str(data["phone"])))
        elif action == "code":
            connected = asyncio.run(complete_login(account, str(data.get("code", "")), str(data.get("password", ""))))
            return JsonResponse({"ok": True, "connected": connected, "status": account.status})
        elif action == "refresh":
            rows = asyncio.run(available_channels(account))
            request.session["telegram_discovered_channels"] = rows
            return JsonResponse({"ok": True, "discovered": rows})
        elif action == "channel":
            discovered = request.session.get("telegram_discovered_channels", [])
            peer_id = str(data.get("peer_id", ""))
            selected = next(row for row in discovered if str(row["peer_id"]) == peer_id)
            channel = configure_channel(
                request.user,
                account,
                selected["peer_id"],
                selected["title"],
                selected.get("username", ""),
                parse_mode=str(data.get("parse_mode", "hybrid")),
                automation="manual",
                template={},
                min_confidence=int(data.get("min_confidence", 80)),
                paper_capital=Decimal(str(data.get("capital", 100))),
            )
            return JsonResponse({"ok": True, "channel_id": channel.pk})
        elif action == "toggle":
            channel = get_object_or_404(TelegramChannel, owner=request.user, pk=int(data["channel_id"]))
            channel.enabled = not channel.enabled
            channel.source.enabled = channel.enabled
            channel.source.save(update_fields=("enabled",))
            channel.save(update_fields=("enabled", "updated_at"))
        elif action == "archive_start":
            channel = get_object_or_404(TelegramChannel, owner=request.user, pk=int(data["channel_id"]))
            job, _ = start_backfill(channel)
            process_backfill_batch.apply_async(args=[job.pk], queue="signals")
            return JsonResponse({"ok": True, "job_id": job.pk}, status=202)
        elif action == "archive_pause":
            job = get_object_or_404(TelegramBackfillJob, owner=request.user, pk=int(data["job_id"]))
            pause_backfill(job)
        elif action == "revoke":
            revoke_telegram_credentials(account)
            TelegramChannel.objects.filter(owner=request.user).update(enabled=False)
        else:
            raise ValidationError("عملیات Telegram معتبر نیست.")
        return JsonResponse({"ok": True, "status": account.status})
    except (ValidationError, ValueError, TypeError, KeyError, StopIteration) as error:
        return JsonResponse({"error": getattr(error, "messages", [str(error)])}, status=400)
