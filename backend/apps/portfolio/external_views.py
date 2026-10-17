"""Explicit read-only details for imported external observations, never adoption."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.operations.models import ExternalObservation

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
    "qty",
    "commission",
    "commissionAsset",
    "isBuyer",
    "free",
    "locked",
)


@login_required
@never_cache
@require_GET
def detail(request, pk):
    item = get_object_or_404(
        ExternalObservation.objects.select_related("account"), account__owner=request.user, pk=pk
    )
    payload = item.payload if isinstance(item.payload, dict) else {}
    fields = [
        (key, payload[key])
        for key in SAFE_FIELDS
        if key in payload and isinstance(payload[key], (str, int, float, bool, type(None)))
    ]
    return render(
        request, "portfolio/external.html", {"item": item, "fields": fields, "nav": "dashboard"}
    )
