"""Private Paper management. Every launch requires explicit POST and UUID."""

import json
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.audit import record_audit
from apps.accounts.security import session_api_required
from apps.tradeplans.models import TradePlan

from .execution import cancel_unsubmitted
from .exits_stop import adjust_stop
from .exits_engine import process_paper_price
from .trailing_rules import configure_trailing
from .intent import queue_paper_trade
from .models import Trade, TradeProtection, TradeEvent


def _owned(user, pk):
    return get_object_or_404(
        Trade.objects.filter(owner=user).select_related("account", "market", "plan", "signal"),
        pk=pk,
    )


def _serialized(trade):
    order = trade.orders.first()
    position = getattr(trade, "position", None)
    return {
        "id": trade.pk,
        "state": trade.state,
        "mode": "paper",
        "account_id": trade.account_id,
        "market_id": trade.market_id,
        "plan_id": trade.plan_id,
        "signal_id": trade.signal_id,
        "quantity": str(trade.quantity),
        "filled_quantity": str(trade.filled_quantity),
        "entry_price": str(trade.entry_price),
        "position_quantity": str(position.quantity) if position else "0",
        "order": {"id": order.pk, "state": order.state, "client_order_id": order.client_order_id}
        if order
        else None,
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
    return render(
        request,
        "trading/detail.html",
        {
            "trade": trade,
            "events": trade.events.all(),
            "orders": trade.orders.all(),
            "nav": "paper",
            "position": getattr(trade, "position", None),
            "protection": getattr(trade, "protection", None),
            "targets": trade.targets.order_by("position"),
            "exit_fills": trade.exit_fills.order_by("-occurred_at")[:25],
        },
    )


@login_required
@require_POST
def launch_trade(request, plan_id):
    get_object_or_404(TradePlan, pk=plan_id, owner=request.user, status="ready")
    try:
        request_key = uuid.UUID(request.POST.get("request_key", ""))
        trade, created = queue_paper_trade(request.user, plan_id, request_key=request_key)
        if created:
            record_audit(
                "paper_trade.queued",
                user=request.user,
                metadata={"trade_id": trade.pk, "plan_id": plan_id},
            )
            messages.success(
                request, "درخواست Paper در Outbox ثبت شد؛ Worker مستقل آن را اجرا می‌کند."
            )
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
            record_audit(
                "paper_trade.queued",
                user=request.user,
                metadata={"trade_id": trade.pk, "plan_id": plan_id},
            )
        return JsonResponse(
            {"trade": _serialized(trade), "created": created}, status=201 if created else 200
        )
    except (KeyError, ValueError, TypeError, ValidationError, IntegrityError) as error:
        return JsonResponse({"error": str(error)}, status=400)


@login_required
@require_POST
def move_stop(request, pk):
    trade = _owned(request.user, pk)
    try:
        adjust_stop(
            request.user, trade.pk, version=int(request.POST.get("version", "0")),
            mode=request.POST.get("mode", ""), price=request.POST.get("price"),
            reason=request.POST.get("reason", ""),
        )
        messages.success(request, "Stop با ثبت رویداد تغییر کرد.")
    except (ValidationError, ValueError) as error:
        messages.error(request, str(error))
    return redirect("paper-trade-detail", pk=pk)


@session_api_required
@never_cache
@require_POST
def api_move_stop(request, pk):
    _owned(request.user, pk)
    if request.content_type != "application/json" or len(request.body) > 4000:
        return JsonResponse({"error":"درخواست JSON معتبر لازم است."}, status=400)
    try:
        body = json.loads(request.body)
        protection, moved = adjust_stop(
            request.user, pk, version=int(body["version"]),
            mode=body["mode"], price=body.get("price"), reason=body.get("reason", ""),
        )
        return JsonResponse({"moved":moved, "stop":str(protection.effective_stop),
                             "version":protection.version})
    except (ValueError, KeyError, TypeError, ValidationError) as error:
        return JsonResponse({"error":str(error)}, status=400)


@login_required
@require_POST
def set_paper_scenario(request, pk):
    _owned(request.user, pk)
    try:
        with transaction.atomic():
            trade = Trade.objects.select_for_update().select_related("account").get(
                pk=pk, owner=request.user
            )
            if (trade.account.environment != "paper" or trade.state != Trade.State.OPEN
                    or trade.account.exchange.adapter_code != "simulator"):
                raise ValidationError("سناریوی قیمت تنها برای Position باز شبیه‌ساز مجاز است.")
            rule = TradeProtection.objects.select_for_update().get(trade=trade)
            if rule.version != int(request.POST.get("version", "0")):
                raise ValidationError("نسخه صفحه قدیمی است.")
            if not rule.paper_scenario:
                rule.paper_scenario = True
                rule.version += 1
                rule.coverage = TradeProtection.Coverage.MONITORED
                rule.save(update_fields=("paper_scenario", "version", "coverage", "updated_at"))
                TradeEvent.objects.create(
                    trade=trade, event_type="PAPER_SCENARIO_ENABLED",
                    payload={"native_stop":False, "feed":"user_test_prices"}
                )
        messages.success(request, "سناریوی تست Paper فعال شد؛ فید خودکار این معامله متوقف است.")
    except (ValidationError, ValueError) as error:
        messages.error(request, str(error))
    return redirect("paper-trade-detail", pk=pk)


@login_required
@require_POST
def paper_price_event(request, pk):
    _owned(request.user, pk)
    try:
        result = process_paper_price(
            pk, price=request.POST.get("price", ""),
            event_key=request.POST.get("tick_key", str(uuid.uuid4())),
            source="paper_scenario",
        )
        messages.success(request, f"نتیجه Tick آزمایشی: {result['status']}")
    except (ValidationError, ValueError) as error:
        messages.error(request, str(error))
    return redirect("paper-trade-detail", pk=pk)


@login_required
@require_POST
def set_trailing(request, pk):
    _owned(request.user, pk)
    try:
        configure_trailing(
            request.user, pk, version=int(request.POST.get("version", "0")),
            step_enabled=request.POST.get("step_enabled") == "on",
            percentage_enabled=request.POST.get("percentage_enabled") == "on",
            distance_percent=request.POST.get("distance_percent", "1"),
            reason=request.POST.get("reason", ""),
        )
        messages.success(request, "قانون trailing با ثبت audit ذخیره شد.")
    except (ValidationError, ValueError) as error:
        messages.error(request, str(error))
    return redirect("paper-trade-detail", pk=pk)


@session_api_required
@never_cache
@require_POST
def api_paper_tick(request, pk):
    _owned(request.user, pk)
    if request.content_type != "application/json" or len(request.body) > 4000:
        return JsonResponse({"error":"JSON معتبر لازم است."}, status=400)
    try:
        body = json.loads(request.body)
        result = process_paper_price(
            pk, price=body["price"],
            event_key=body.get("tick_key", str(uuid.uuid4())),
            source="paper_scenario",
        )
        return JsonResponse({"result":result, "real_orders":False})
    except (ValueError, KeyError, TypeError, ValidationError) as error:
        return JsonResponse({"error":str(error)}, status=400)


@session_api_required
@never_cache
@require_POST
def api_trailing_update(request, pk):
    _owned(request.user, pk)
    if request.content_type != "application/json" or len(request.body) > 4000:
        return JsonResponse({"error":"JSON معتبر لازم است."}, status=400)
    try:
        body = json.loads(request.body)
        rule = configure_trailing(
            request.user, pk, version=int(body["version"]),
            step_enabled=body["step_enabled"] is True,
            percentage_enabled=body["percentage_enabled"] is True,
            distance_percent=body["distance_percent"],
            reason=body.get("reason", ""),
        )
        return JsonResponse({"version":rule.version,
                             "effective_stop":str(rule.effective_stop),
                             "percentage_active":rule.percentage_active,
                             "real_orders":False})
    except (ValueError, KeyError, TypeError, ValidationError) as error:
        return JsonResponse({"error":str(error)}, status=400)
