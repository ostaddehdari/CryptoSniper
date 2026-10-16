import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.security import session_api_required
from apps.signals.models import Signal

from .forms import ManualTradeForm
from .models import TradePlan
from .service import approve_plan, create_draft, update_draft


def owned(user, pk):
    return get_object_or_404(
        TradePlan.objects.select_related("market", "market__exchange", "exchange_account"),
        owner=user,
        pk=pk,
    )


@login_required
@never_cache
@require_GET
def list_plans(request):
    plans = TradePlan.objects.filter(owner=request.user).select_related(
        "market", "exchange_account"
    )[:100]
    return render(request, "tradeplans/list.html", {"plans": plans, "nav": "manual"})


def _form_context(form, request, *, plan=None):
    accounts = list(form.fields["account"].queryset)
    markets = list(form.fields["market"].queryset.select_related("exchange"))
    form.fields["account"].widget.attrs["data-accounts"] = "1"
    return {"form": form, "accounts": accounts, "markets": markets, "plan": plan, "nav": "manual"}


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def new_plan(request):
    initial = {}
    signal_id = request.GET.get("signal")
    if signal_id and request.method == "GET":
        signal = get_object_or_404(
            Signal, pk=signal_id, owner=request.user, status=Signal.Status.APPROVED
        )
        initial = {
            "origin_signal": signal.pk,
            "account": signal.exchange_account_id,
            "market": signal.market_id,
            "source": "manual",
            "side": signal.side,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "leverage": 1,
            "capital": 50,
            "trailing_distance": 1,
            "trailing_sl": bool(signal.parsed_payload.get("trailing_sl", False)),
            "percentage_trailing": bool(signal.parsed_payload.get("percentage_trailing", False)),
        }
        for target in signal.targets.order_by("position"):
            initial[f"tp{target.position}"] = target.price
    form = ManualTradeForm(
        request.user, request.POST if request.method == "POST" else None, initial=initial
    )
    if request.method == "POST" and form.is_valid():
        try:
            plan, _ = create_draft(request.user, form.cleaned_data)
            return redirect("manual-preview", pk=plan.pk)
        except (ValidationError, IntegrityError) as error:
            form.add_error(None, str(error))
    return render(request, "tradeplans/form.html", _form_context(form, request))


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def edit_plan(request, pk):
    plan = owned(request.user, pk)
    if plan.status != TradePlan.Status.DRAFT:
        return redirect("manual-preview", pk=pk)
    initial = {
        "account": plan.exchange_account_id,
        "market": plan.market_id,
        "source": "manual",
        "origin_signal": plan.origin_signal_id,
        "side": plan.side,
        "entry_price": plan.entry_price,
        "stop_loss": plan.stop_loss,
        "tp1": plan.tp1,
        "tp2": plan.tp2,
        "tp3": plan.tp3,
        "capital": plan.capital,
        "leverage": plan.leverage,
        "trailing_sl": plan.trailing_sl,
        "percentage_trailing": plan.percentage_trailing,
        "trailing_distance": plan.trailing_distance,
        "client_token": plan.client_token,
    }
    form = ManualTradeForm(
        request.user, request.POST if request.method == "POST" else None, initial=initial
    )
    if request.method == "POST" and form.is_valid():
        try:
            expected = int(request.POST.get("revision", "0"))
            update_draft(plan, form.cleaned_data, expected)
            return redirect("manual-preview", pk=pk)
        except (ValidationError, ValueError) as error:
            form.add_error(None, str(error))
    return render(request, "tradeplans/form.html", _form_context(form, request, plan=plan))


@login_required
@never_cache
@require_GET
def preview_plan(request, pk):
    plan = owned(request.user, pk)
    return render(
        request,
        "tradeplans/preview.html",
        {
            "plan": plan,
            "nav": "manual",
            "paper_request_key": uuid.uuid4(),
            "snapshot": plan.approved_snapshot if plan.status == "ready" else plan.preview,
        },
    )


@login_required
@require_POST
def confirm_plan(request, pk):
    plan = owned(request.user, pk)
    try:
        revision = int(request.POST.get("revision", "0"))
        approve_plan(request.user, plan.pk, revision)
        messages.success(request, "برنامه تأیید و Snapshot ثابت ثبت شد؛ هیچ سفارشی ارسال نشد.")
    except (ValueError, ValidationError) as error:
        messages.error(request, str(error))
    return redirect("manual-preview", pk=pk)


def _serialized(plan):
    return {
        "id": plan.pk,
        "status": plan.status,
        "revision": plan.revision,
        "market_id": plan.market_id,
        "account_id": plan.exchange_account_id,
        "client_token": str(plan.client_token),
        "snapshot": plan.approved_snapshot if plan.status == "ready" else plan.preview,
        "orders_submitted": 0,
    }


@session_api_required
@never_cache
@require_GET
def api_plan(request, pk):
    return JsonResponse({"plan": _serialized(owned(request.user, pk))})


@session_api_required
@never_cache
@require_http_methods(["POST"])
def api_create(request):
    try:
        import json

        if request.content_type != "application/json":
            return JsonResponse({"error": "application/json لازم است"}, status=415)
        body = json.loads(request.body)
        if not isinstance(body, dict):
            raise ValueError("invalid json")
        form = ManualTradeForm(request.user, body)
        if not form.is_valid():
            return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
        plan, created = create_draft(request.user, form.cleaned_data)
        return JsonResponse(
            {"plan": _serialized(plan), "created": created}, status=201 if created else 200
        )
    except (ValueError, ValidationError, IntegrityError) as e:
        return JsonResponse({"error": str(e)}, status=400)


@session_api_required
@never_cache
@require_http_methods(["POST"])
def api_confirm(request, pk):
    import json

    owned(request.user, pk)
    try:
        body = (
            json.loads(request.body) if request.content_type == "application/json" else request.POST
        )
        revision = int(body.get("revision", 0))
        plan = approve_plan(request.user, pk, revision)
        return JsonResponse({"plan": _serialized(plan)})
    except (ValueError, ValidationError) as e:
        return JsonResponse({"error": str(e)}, status=400)


@session_api_required
@never_cache
@require_http_methods(["POST"])
def api_edit(request, pk):
    import json

    plan = owned(request.user, pk)
    if request.content_type != "application/json":
        return JsonResponse({"error": "application/json لازم است"}, status=415)
    try:
        payload = json.loads(request.body)
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        revision = int(payload.get("revision", 0))
        form = ManualTradeForm(request.user, payload)
        if not form.is_valid():
            return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
        result = update_draft(plan, form.cleaned_data, revision)
        return JsonResponse({"plan": _serialized(result)})
    except (ValueError, ValidationError) as error:
        return JsonResponse({"error": str(error)}, status=400)
