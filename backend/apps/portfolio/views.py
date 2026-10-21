from time import perf_counter

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.security import session_api_required
from apps.alerts.models import Notification, PriceAlert
from apps.exchanges.models import LiveSpotOrder, UserExchangeAccount
from apps.operations.models import ExternalObservation
from apps.signals.models import Signal
from apps.reports.models import PerformanceAggregate

from .balances import balances_for
from .metrics import summarize, trade_queryset


def dashboard_context(user, params):
    start = perf_counter()
    all_accounts = list(
        UserExchangeAccount.objects.filter(owner=user)
        .select_related("exchange", "accountcontrol")
        .order_by("pk")
    )
    selected = str(params.get("account", ""))
    accounts = all_accounts
    if selected:
        account = get_object_or_404(
            UserExchangeAccount, pk=selected if selected.isdigit() else 0, owner=user
        )
        accounts = [a for a in all_accounts if a.pk == account.pk]
    summary = summarize(
        user,
        trade_queryset(user)
        .filter(account_id__in=[a.pk for a in accounts])
        .order_by("-created_at"),
    )
    balances, cache_ok = balances_for(accounts, user.base_currency)
    signals = Signal.objects.filter(owner=user).select_related("source")
    if selected:
        signals = signals.filter(exchange_account_id=selected)
    result = {
        **summary,
        "accounts": all_accounts,
        "account_cards": balances,
        "selected_account": selected,
        "recent_trades": summary["trades"][:6],
        "active_signals": signals.filter(
            status__in=["new", "parsed", "needs_review", "approved"]
        ).count(),
        "recent_signals": list(signals.order_by("-created_at")[:5]),
        "recent_alerts": list(
            PriceAlert.objects.filter(owner=user)
            .select_related("market")
            .order_by("-updated_at")[:5]
        ),
        "important_notifications": list(
            Notification.objects.filter(owner=user, in_app=True, read_at__isnull=True).order_by(
                "-pk"
            )[:3]
        ),
        "external": list(
            ExternalObservation.objects.filter(account_id__in=[a.pk for a in accounts])
            .select_related("account")
            .order_by("-observed_at")[:8]
        ),
        "cache_ok": cache_ok and summary["cache_ok"],
        "as_of": timezone.now(),
        "error": False,
    }
    result["build_ms"] = round((perf_counter() - start) * 1000, 2)
    return result


@login_required
@never_cache
@require_GET
def dashboard(request):
    return render(
        request,
        "core/dashboard.html",
        {
            "nav": "dashboard",
            "accounts": UserExchangeAccount.objects.filter(owner=request.user),
            "selected_account": request.GET.get("account", ""),
        },
    )


@login_required
@never_cache
@require_GET
def fragment(request):
    try:
        context = dashboard_context(request.user, request.GET)
    except DatabaseError:
        return render(request, "portfolio/error.html", status=503)
    return render(request, "portfolio/panels.html", context)


@session_api_required
@never_cache
@require_GET
def api_dashboard(request):
    try:
        data = dashboard_context(request.user, request.GET)
    except DatabaseError:
        return JsonResponse({"error": "dependencies_unavailable"}, status=503)
    month = timezone.localdate().replace(day=1)
    monthly = (
        PerformanceAggregate.objects.filter(
            owner=request.user,
            period_kind="month",
            period_start=month,
            dimension_kind="total",
            dimension_value="all",
            currency=request.user.base_currency,
        )
        .order_by("-updated_at")
        .first()
    )
    account_rows = []
    for c in data["account_cards"]:
        usdt = next((row for row in c["rows"] if row["asset"] == "USDT" and row["wallet"] == "spot"), None)
        account_rows.append(
            {
                "id": c["account"].pk,
                "label": c["account"].label,
                "exchange": c["account"].exchange.name,
                "status": c["account"].status,
                "base_currency": c["base_currency"],
                "known_valuation": c["valuation"],
                "known_available_valuation": c["available_valuation"],
                "complete": c["complete"],
                "unvalued_assets": c["unknown"],
                "free_usdt": usdt["free"] if usdt else None,
                "balances": c["rows"],
            }
        )
    recent_live = (
        LiveSpotOrder.objects.filter(owner=request.user)
        .select_related("account__exchange", "market")
        .order_by("-updated_at")[:6]
    )
    return JsonResponse(
        {
            "as_of": data["as_of"],
            "open_trades": sum(1 for item in recent_live if item.state in {"pending", "submitting", "open", "partial"}),
            "today_trades": data["today_count"],
            "active_signals": data["active_signals"],
            "connected_accounts": sum(1 for item in data["accounts"] if item.status == "connected"),
            "pnl": data["buckets"],
            "monthly_net_pnl": monthly.net_realized if monthly else None,
            "monthly_net_complete": bool(monthly and monthly.unknown_count == 0),
            "cache_ok": data["cache_ok"],
            "accounts": account_rows,
            "recent_orders": [_live_order_payload(item) for item in recent_live],
            "recent_signals": [
                {
                    "id": item.pk,
                    "status": item.status,
                    "source": item.source.name,
                    "side": item.side,
                    "entry": item.entry_price,
                    "created_at": item.created_at,
                }
                for item in data["recent_signals"]
            ],
            "recent_alerts": [
                {
                    "id": item.pk,
                    "market": item.market.symbol,
                    "enabled": item.enabled,
                    "updated_at": item.updated_at,
                }
                for item in data["recent_alerts"]
            ],
            "recent_external": [_safe_external(item) for item in data["external"]],
            "build_ms": data["build_ms"],
        }
    )


SAFE_EXTERNAL_FIELDS = {
    "symbol", "orderId", "clientOrderId", "status", "origQty", "executedQty",
    "price", "side", "type", "time", "updateTime", "id", "qty",
    "commission", "commissionAsset", "isBuyer", "free", "locked",
}


def _safe_external(item):
    payload = item.payload if isinstance(item.payload, dict) else {}
    return {
        "id": item.pk,
        "account_id": item.account_id,
        "exchange": item.account.exchange.name,
        "kind": item.kind,
        "external_id": item.external_id,
        "observed_at": item.observed_at,
        "payload": {
            key: payload[key]
            for key in SAFE_EXTERNAL_FIELDS
            if key in payload and isinstance(payload[key], (str, int, float, bool, type(None)))
        },
    }


def _live_order_payload(order):
    return {
        "id": order.pk,
        "account_id": order.account_id,
        "exchange": order.account.exchange.name,
        "market": order.market.symbol,
        "side": order.side,
        "order_type": order.order_type,
        "amount": order.amount,
        "price": order.price,
        "filled_amount": order.filled_amount,
        "average_price": order.average_price,
        "state": order.state,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
        "source": "cryptosniper",
    }


@login_required
@never_cache
@require_GET
def trades(request):
    return render(request, "portfolio/trades.html", {"nav": "trades"})


@session_api_required
@never_cache
@require_GET
def api_trades(request):
    accounts = UserExchangeAccount.objects.for_user(request.user).select_related("exchange")
    account_ids = list(accounts.values_list("pk", flat=True))
    live_orders = (
        LiveSpotOrder.objects.filter(owner=request.user, account_id__in=account_ids)
        .select_related("account__exchange", "market")
        .order_by("-updated_at")[:100]
    )
    external = (
        ExternalObservation.objects.filter(account_id__in=account_ids)
        .select_related("account__exchange")
        .order_by("-observed_at")[:100]
    )
    return JsonResponse(
        {
            "orders": [_live_order_payload(item) for item in live_orders],
            "external": [_safe_external(item) for item in external],
        }
    )
