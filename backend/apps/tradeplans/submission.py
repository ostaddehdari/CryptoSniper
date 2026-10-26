"""One atomic, idempotent manual entry with its immutable risk/trailing snapshot."""

import logging
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from kombu.exceptions import OperationalError

from apps.accounts.security import has_recent_step_up, session_api_required
from apps.exchanges.live_orders import queue_live_spot_order
from apps.exchanges.models import LiveSpotOrder
from apps.exchanges.tasks import live_spot_order

from .forms import ManualTradeForm
from .service import _hash, approve_plan, create_draft

logger = logging.getLogger(__name__)


def _dispatch(order_id):
    try:
        live_spot_order.apply_async(args=[order_id], queue="orders")
    except OperationalError:
        # The existing Beat dispatcher recovers durable PENDING rows independently.
        logger.warning("Entry dispatch deferred; durable order %s remains pending", order_id)


@transaction.atomic
def submit(owner, data, key):
    # All requests for this owner serialize before draft creation and account locking.
    get_user_model().objects.select_for_update().get(pk=owner.pk)
    existing = (
        LiveSpotOrder.objects.select_related("source_plan")
        .filter(owner=owner, request_key=key)
        .first()
    )
    if existing:
        if not existing.source_plan or existing.source_plan.preview.get("form_digest") != _hash(
            data
        ):
            raise ValidationError("این شناسه برای فرم دیگری استفاده شده است؛ سفارش جدید ثبت نشد.")
        return existing, False
    plan, _ = create_draft(owner, data)
    plan = approve_plan(owner, plan.pk, plan.revision)
    if plan.market.market_type != "spot" or plan.side != "long":
        raise ValidationError("ارسال این نسخه فقط Spot Long است.")
    order, created = queue_live_spot_order(
        owner,
        data["account"],
        {
            "request_key": key,
            "market": data["market"],
            "side": "buy",
            "amount": Decimal(plan.approved_snapshot["quantity"]),
            "price": plan.entry_price,
            "source_plan": plan,
        },
    )
    if created:
        transaction.on_commit(lambda: _dispatch(order.pk))
    return order, created


@session_api_required
@never_cache
@require_POST
def api_submit(request):
    if not has_recent_step_up(request):
        return JsonResponse(
            {"error": "step_up_required", "verify_url": reverse("security-step-up")}, status=403
        )
    from apps.core.react_views import _body, _live_order_payload

    try:
        body = _body(request)
        if body.get("confirmed") is not True:
            raise ValidationError("تأیید صریح ارسال سفارش لازم است.")
        key = uuid.UUID(str(body.get("request_key", "")))
        body["client_token"] = str(key)
        form = ManualTradeForm(request.user, body)
        if not form.is_valid():
            return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
        order, created = submit(request.user, form.cleaned_data, key)
        return JsonResponse(
            {
                "order": _live_order_payload(order),
                "created": created,
                "plan_id": order.source_plan_id,
                "automatic_exits_active": False,
            },
            status=201 if created else 200,
        )
    except (ValidationError, ValueError, TypeError) as error:
        return JsonResponse({"error": getattr(error, "messages", [str(error)])}, status=400)
