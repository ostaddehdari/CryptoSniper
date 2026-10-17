import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.security import session_api_required

from .forms import AlertForm
from .models import PriceAlert
from .service import save_alert


def _owned(owner, pk):
    return get_object_or_404(PriceAlert, owner=owner, pk=pk)


@login_required
@never_cache
@require_GET
def center(request):
    return render(
        request,
        "alerts/list.html",
        {
            "nav": "alerts",
            "items": PriceAlert.objects.filter(owner=request.user)
            .select_related("market", "trade")
            .order_by("-pk")[:200],
        },
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def edit(request, pk=None):
    instance = _owned(request.user, pk) if pk else None
    initial = {key: request.GET[key] for key in ("market", "trade") if key in request.GET}
    form = AlertForm(request.user, request.POST or None, instance=instance, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            save_alert(request.user, form)
            messages.success(
                request, "هشدار ذخیره شد؛ فقط اطلاع‌رسانی می‌کند. مبنای قیمت تازه ثبت شد."
            )
            return redirect("alerts")
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, "alerts/form.html", {"form": form, "nav": "alerts", "editing": bool(pk)})


@login_required
@require_POST
@transaction.atomic
def disable(request, pk):
    alert = get_object_or_404(PriceAlert.objects.select_for_update(), owner=request.user, pk=pk)
    if str(alert.version) != request.POST.get("version"):
        messages.error(request, "هشدار تغییر کرده؛ صفحه را تازه کنید.")
    else:
        alert.enabled, alert.status = False, "disabled"
        alert.version += 1
        alert.save()
    return redirect("alerts")


@session_api_required
@never_cache
@require_http_methods(["GET", "POST"])
def api_list(request):
    if request.method == "GET":
        return JsonResponse(
            {
                "alerts": [
                    {
                        "id": a.pk,
                        "title": a.title,
                        "market_id": a.market_id,
                        "trade_id": a.trade_id,
                        "kind": a.kind,
                        "threshold": str(a.threshold),
                        "reference_price": str(a.reference_price),
                        "reference_at": a.reference_at.isoformat(),
                        "enabled": a.enabled,
                        "version": a.version,
                        "status": a.status,
                        "fire_count": a.fire_count,
                    }
                    for a in PriceAlert.objects.filter(owner=request.user).order_by("-pk")[:200]
                ]
            }
        )
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError
        instance = _owned(request.user, data["id"]) if data.get("id") else None
        form = AlertForm(request.user, data, instance=instance)
        if not form.is_valid():
            return JsonResponse({"errors": form.errors}, status=400)
        alert = save_alert(request.user, form)
        return JsonResponse(
            {"id": alert.pk, "version": alert.version}, status=200 if instance else 201
        )
    except (ValueError, TypeError, ValidationError) as error:
        return JsonResponse({"error": str(error)}, status=400)
