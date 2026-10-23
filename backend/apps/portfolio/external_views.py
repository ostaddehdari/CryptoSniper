"""External observation views and explicit Spot-long management adoption."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.security import step_up_required
from apps.operations.models import ExternalObservation, ExternalTradePolicy

from .external_management import apply_external_policy
from .external_utils import normalized_external
from .forms import ExternalTradePolicyForm

SAFE_FIELDS = (
    "symbol",
    "orderId",
    "clientOrderId",
    "status",
    "origQty",
    "executedQty",
    "price",
    "side",
    "type",
    "time",
    "updateTime",
    "id",
    "tradeId",
    "qty",
    "quantity",
    "amount",
    "filled_amount",
    "average_price",
    "avgPrice",
    "commission",
    "commissionAsset",
    "isBuyer",
    "created_at",
)


def _owned(user, pk):
    return get_object_or_404(
        ExternalObservation.objects.select_related("account__exchange"),
        account__owner=user,
        pk=pk,
    )


@login_required
@never_cache
@require_GET
def list_external(request):
    items = list(
        ExternalObservation.objects.filter(
            account__owner=request.user, kind__in=("order", "fill", "history")
        )
        .select_related("account__exchange")
        .order_by("-observed_at")[:200]
    )
    rows = [{"item": item, **normalized_external(item)} for item in items]
    return render(
        request,
        "portfolio/external_list.html",
        {"rows": rows, "nav": "dashboard"},
    )


@login_required
@never_cache
@require_GET
def detail(request, pk):
    item = _owned(request.user, pk)
    payload = item.payload if isinstance(item.payload, dict) else {}
    normalized = normalized_external(item)
    fields = [
        (key, payload[key])
        for key in SAFE_FIELDS
        if key in payload and isinstance(payload[key], (str, int, float, bool, type(None)))
    ]
    policy = (
        ExternalTradePolicy.objects.filter(observation=item).select_related("exit_order").first()
    )
    form = ExternalTradePolicyForm(item=item, instance=policy)
    return render(
        request,
        "portfolio/external.html",
        {
            "item": item,
            "fields": fields,
            "normalized": normalized,
            "policy": policy,
            "form": form,
            "live_enabled": settings.LIVE_TRADING_ENABLED,
            "nav": "dashboard",
        },
    )


@login_required
@require_POST
@step_up_required
def manage(request, pk):
    item = _owned(request.user, pk)
    policy = ExternalTradePolicy.objects.filter(observation=item).first()
    form = ExternalTradePolicyForm(request.POST, item=item, instance=policy)
    try:
        if not settings.LIVE_TRADING_ENABLED:
            raise ValidationError("اجرای Live روی سرور خاموش است؛ سیاست خارجی فعال نشد.")
        if not form.is_valid():
            errors = [str(v) for values in form.errors.values() for v in values]
            raise ValidationError("؛ ".join(errors))
        apply_external_policy(request.user, item.pk, form.cleaned_data)
        messages.success(
            request,
            "مدیریت معامله خارجی فعال شد؛ خروج فقط از مسیر امن Live Spot "
            "و بدون برداشت انجام می‌شود.",
        )
    except ValidationError as error:
        messages.error(request, "؛ ".join(getattr(error, "messages", [str(error)])))
    return redirect("external-detail", pk=pk)


@login_required
@require_POST
@step_up_required
def disable_management(request, pk):
    item = _owned(request.user, pk)
    policy = ExternalTradePolicy.objects.filter(observation=item).first()
    if policy and policy.state == ExternalTradePolicy.State.ACTIVE:
        policy.state = ExternalTradePolicy.State.DISABLED
        policy.version += 1
        policy.save(update_fields=("state", "version", "updated_at"))
        messages.success(request, "مدیریت خودکار این معامله خارجی غیرفعال شد.")
    return redirect("external-detail", pk=pk)
