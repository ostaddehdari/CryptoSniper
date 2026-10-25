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
from apps.exchanges.models import UserExchangeAccount
from apps.operations.models import ExternalObservation
from apps.signals.models import Signal

from .balances import balances_for
from .external_utils import normalized_external
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
        "external": [
            {"item": item, **normalized_external(item)}
            for item in ExternalObservation.objects.filter(
                account_id__in=[a.pk for a in accounts],
                kind__in=("order", "fill", "history"),
            )
            .select_related("account__exchange")
            .order_by("-observed_at")[:8]
        ],
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
    return JsonResponse(
        {
            "as_of": data["as_of"],
            "open_trades": data["open_count"],
            "today_trades": data["today_count"],
            "active_signals": data["active_signals"],
            "pnl": data["buckets"],
            "cache_ok": data["cache_ok"],
            "accounts": [
                {
                    "id": c["account"].pk,
                    "base_currency": c["base_currency"],
                    "known_valuation": c["valuation"],
                    "known_available_valuation": c["available_valuation"],
                    "complete": c["complete"],
                    "unvalued_assets": c["unknown"],
                    "balances": c["rows"],
                }
                for c in data["account_cards"]
            ],
            "build_ms": data["build_ms"],
        }
    )
