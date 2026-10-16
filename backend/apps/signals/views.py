import json
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.security import session_api_required

from .forms import ReceiveForm, ReviewForm
from .models import Signal, SignalSource
from .services import receive_signal, snapshot, transition, update_parsed
from .sources import get_default_source


def owned(user, pk):
    return get_object_or_404(
        Signal.objects.filter(owner=user).select_related(
            "source", "raw_signal", "market", "exchange_account"
        ),
        pk=pk,
    )


def filtered(user, params):
    qs = Signal.objects.filter(owner=user).select_related("source", "raw_signal", "market")
    status = params.get("status", "").strip()
    if status in Signal.Status.values:
        qs = qs.filter(status=status)
    method = params.get("method", "").strip()
    if method in SignalSource.Method.values:
        qs = qs.filter(source__method=method)
    after = params.get("after", "").strip()
    if after:
        try:
            date = datetime.strptime(after, "%Y-%m-%d").date()
            qs = qs.filter(created_at__date__gte=date)
        except ValueError:
            pass
    before = params.get("before", "").strip()
    if before:
        try:
            date = datetime.strptime(before, "%Y-%m-%d").date()
            qs = qs.filter(created_at__date__lte=date)
        except ValueError:
            pass
    return qs.order_by("-created_at")


@login_required
@never_cache
@require_GET
def inbox(request):
    return render(
        request,
        "signals/inbox.html",
        {
            "nav": "inbox",
            "items": filtered(request.user, request.GET)[:100],
            "statuses": Signal.Status.choices,
            "methods": SignalSource.Method.choices,
        },
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def receive(request):
    form = ReceiveForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        source = get_default_source(request.user, form.cleaned_data["method"])
        try:
            signal, _, _ = receive_signal(request.user, source, text=form.cleaned_data["text"])
            messages.success(request, "متن اصلی ذخیره شد؛ برای تأیید ابتدا آن را بررسی کنید.")
            return redirect("inbox-detail", pk=signal.pk)
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, "signals/receive.html", {"nav": "inbox", "form": form})


@login_required
@never_cache
@require_GET
def detail(request, pk):
    item = owned(request.user, pk)
    initial = {
        "account_id": item.exchange_account_id,
        "market_id": item.market_id,
        "side": item.side or "long",
        "entry_price": item.entry_price,
        "stop_loss": item.stop_loss,
        "revision": item.revision,
    }
    for target in item.targets.order_by("position"):
        initial[f"tp{target.position}"] = target.price
    form = ReviewForm(request.user, initial=initial)
    return render(
        request,
        "signals/detail.html",
        {
            "nav": "inbox",
            "item": item,
            "form": form,
            "historical": item.history.order_by("-revision"),
            "raw_revisions": item.raw_signal.revisions.order_by("-version"),
        },
    )


@login_required
@require_POST
def edit(request, pk):
    item = owned(request.user, pk)
    form = ReviewForm(request.user, request.POST)
    if form.is_valid():
        try:
            update_parsed(
                request.user,
                item.pk,
                expected_revision=form.cleaned_data["revision"],
                data=form.structured(),
                reason=form.cleaned_data["reason"],
            )
            messages.success(request, "نسخه بازبینی‌شده ثبت شد.")
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
    else:
        messages.error(request, "مقادیر فرم معتبر نیستند؛ همه فیلدها را بررسی کنید.")
    return redirect("inbox-detail", pk=pk)


@login_required
@require_POST
def action(request, pk):
    item = owned(request.user, pk)
    try:
        revision = int(request.POST.get("revision", "0"))
        transition(
            request.user,
            item.pk,
            expected_revision=revision,
            action=request.POST.get("action", ""),
            reason=request.POST.get("reason", ""),
        )
        messages.success(request, "وضعیت با ثبت تاریخچه تغییر کرد؛ سفارشی ارسال نشد.")
    except (ValueError, ValidationError) as error:
        messages.error(request, str(error))
    return redirect("inbox-detail", pk=pk)


def _serialize(item):
    return {
        "id": item.pk,
        "status": item.status,
        "revision": item.revision,
        "source_id": item.source_id,
        "source_method": item.source.method,
        "raw": {
            "id": item.raw_signal_id,
            "original_text": item.raw_signal.original_text,
            "received_version": item.raw_signal.received_version,
            "revisions": item.raw_signal.revision_number,
        },
        "structured": snapshot(item),
        "approved_snapshot": item.approved_snapshot if item.status == "approved" else None,
        "execution_enabled": False,
    }


@session_api_required
@never_cache
@require_GET
def api_list(request):
    rows = filtered(request.user, request.GET)[:100]
    return JsonResponse(
        {
            "items": [
                {
                    "id": item.pk,
                    "status": item.status,
                    "source_method": item.source.method,
                    "revision": item.revision,
                }
                for item in rows
            ],
            "execution_enabled": False,
        }
    )


@session_api_required
@never_cache
@require_GET
def api_detail(request, pk):
    return JsonResponse({"signal": _serialize(owned(request.user, pk))})


def _json_body(request):
    if request.content_type != "application/json":
        raise ValidationError("Content-Type باید application/json باشد.")
    if len(request.body) > 200000:
        raise ValidationError("حجم درخواست بیش از حد مجاز است.")
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError) as error:
        raise ValidationError("بدنه JSON نامعتبر است.") from error
    if not isinstance(payload, dict):
        raise ValidationError("JSON باید یک شیء باشد.")
    return payload


@session_api_required
@never_cache
@require_POST
def api_receive(request):
    try:
        body = _json_body(request)
        form = ReceiveForm({"method": body.get("method"), "text": body.get("text")})
        if not form.is_valid():
            return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
        source = get_default_source(request.user, form.cleaned_data["method"])
        signal, created, revised = receive_signal(
            request.user,
            source,
            text=form.cleaned_data["text"],
            payload=body.get("payload", {}),
            external_id=str(body.get("external_id", "")),
        )
        return JsonResponse(
            {"signal": _serialize(signal), "created": created, "revised": revised},
            status=201 if created else 200,
        )
    except ValidationError as error:
        return JsonResponse({"error": error.messages}, status=400)


@session_api_required
@never_cache
@require_POST
def api_edit(request, pk):
    item = owned(request.user, pk)
    try:
        body = _json_body(request)
        form = ReviewForm(request.user, body)
        if not form.is_valid():
            return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
        signal = update_parsed(
            request.user,
            item.pk,
            expected_revision=form.cleaned_data["revision"],
            data=form.structured(),
            reason=form.cleaned_data["reason"],
        )
        return JsonResponse({"signal": _serialize(signal)})
    except ValidationError as error:
        return JsonResponse({"error": error.messages}, status=400)


@session_api_required
@never_cache
@require_POST
def api_action(request, pk):
    item = owned(request.user, pk)
    try:
        body = _json_body(request)
        signal = transition(
            request.user,
            item.pk,
            expected_revision=int(body.get("revision", 0)),
            action=body.get("action", ""),
            reason=str(body.get("reason", "")),
        )
        return JsonResponse({"signal": _serialize(signal)})
    except (ValidationError, ValueError, TypeError) as error:
        return JsonResponse({"error": str(error)}, status=400)
