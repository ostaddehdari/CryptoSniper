"""Private Paper management. Every launch requires explicit POST and UUID."""
import json
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.audit import record_audit
from apps.accounts.security import session_api_required
from apps.tradeplans.models import TradePlan

from .execution import cancel_unsubmitted
from .intent import queue_paper_trade
from .models import Trade


def _owned(user, pk):
    return get_object_or_404(
        Trade.objects.filter(owner=user).select_related(
            "account", "market", "plan", "signal"
        ), pk=pk
    )


def _serialized(trade):
    order = trade.orders.first()
    position = getattr(trade, "position", None)
    return {
        "id": trade.pk, "state": trade.state, "mode": "paper",
        "account_id": trade.account_id, "market_id": trade.market_id,
        "plan_id": trade.plan_id, "signal_id": trade.signal_id,
        "quantity": str(trade.quantity), "filled_quantity": str(trade.filled_quantity),
        "entry_price": str(trade.entry_price),
        "position_quantity": str(position.quantity) if position else "0",
        "order": {
            "id": order.pk, "state": order.state, "client_order_id": order.client_order_id
        } if order else None,
        "execution_enabled_on_live": False,
    }


@login_required
@never_cache
@require_GET
def list_trades(request):
    trades = Trade.objects.filter(owner=request.user).select_related("market", "account")[:100]
    return render(request, "trading/list.html", {"trades": trades, "nav": "paper"})


@login_required
@never_cache
@require_GET
def trade_detail(request, pk):
    trade = _owned(request.user, pk)
    return render(request, "trading/detail.html", {
        "trade": trade, "events": trade.events.all(),
        "orders": trade.orders.all(), "nav": "paper",
        "position": getattr(trade, "position", None),
    })


@login_required
@require_POST
def launch_trade(request, plan_id):
    get_object_or_404(TradePlan, pk=plan_id, owner=request.user, status="ready")
    try:
        request_key = uuid.UUID(request.POST.get("request_key", ""))
        trade, created = queue_paper_trade(
            request.user, plan_id, request_key=request_key
        )
        if created:
            record_audit("paper_trade.queued", user=request.user,
                         metadata={"trade_id": trade.pk, "plan_id": plan_id})
            messages.success(request, "درخواست Paper در Outbox ثبت شد؛ Worker مستقل آن را اجرا می‌کند.")
        return redirect("paper-trade-detail", pk=trade.pk)
    except (ValueError, ValidationError, IntegrityError) as error:
        messages.error(request, str(error))
        return redirect("manual-preview", pk=plan_id)


@login_required
@require_POST
def cancel_trade(request, pk):
    _owned(request.user, pk)
    try:
        cancel_unsubmitted(request.user, pk)
        record_audit("paper_trade.cancelled", user=request.user, metadata={"trade_id": pk})
        messages.success(request, "درخواست Paper پیش از ارسال لغو شد.")
    except ValidationError as error:
        messages.error(request, str(error))
    return redirect("paper-trade-detail", pk=pk)


@session_api_required
@never_cache
@require_GET
def api_trade_detail(request, pk):
    return JsonResponse({"trade": _serialized(_owned(request.user, pk))})


@session_api_required
@never_cache
@require_POST
def api_trades(request):
    if request.content_type != "application/json":
        return JsonResponse({"error": "application/json لازم است"}, status=415)
    if len(request.body) > 16000:
        return JsonResponse({"error": "درخواست خیلی بزرگ است"}, status=413)
    try:
        body = json.loads(request.body)
        if not isinstance(body, dict):
            raise ValueError("JSON object required")
        plan_id = int(body["plan_id"])
        get_object_or_404(TradePlan, owner=request.user, pk=plan_id, status="ready")
        request_key = uuid.UUID(body["request_key"])
        trade, created = queue_paper_trade(request.user, plan_id, request_key=request_key)
        if created:
            record_audit("paper_trade.queued", user=request.user,
                         metadata={"trade_id": trade.pk, "plan_id": plan_id})
        return JsonResponse({"trade": _serialized(trade), "created": created},
                            status=201 if created else 200)
    except (KeyError, ValueError, TypeError, ValidationError, IntegrityError) as error:
        return JsonResponse({"error": str(error)}, status=400)
