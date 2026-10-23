"""Owner-scoped operations: stop new entries; protective exits keep running."""

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.audit import record_audit
from apps.accounts.security import has_recent_step_up, session_api_required
from apps.exchanges.models import UserExchangeAccount

from .models import AccountControl, ExternalObservation, RecoveryIssue, WorkerHeartbeat


@session_api_required
@never_cache
@require_GET
def api_acceptance(request):
    from .acceptance import base_product_acceptance

    response = JsonResponse(base_product_acceptance())
    response["Cache-Control"] = "no-store"
    return response


@session_api_required
@never_cache
@require_GET
def api_host_capabilities(request):
    from .hosting import hosting_capabilities

    report = hosting_capabilities()
    response = JsonResponse(report, status=200 if report["status"] == "ready" else 503)
    response["Cache-Control"] = "no-store"
    return response


def health_context(user):
    accounts = list(
        UserExchangeAccount.objects.filter(owner=user, environment="live")
        .exclude(status="disabled")
        .exclude(exchange__adapter_code="simulator")
        .exclude(exchange__code="binance")
        .select_related("exchange")
    )
    cutoff = timezone.now() - timedelta(seconds=95)
    workers = [
        {
            "queue": h.queue,
            "fresh": h.seen_at >= cutoff,
            "seen_at": h.seen_at,
            "lag_seconds": h.lag_seconds,
        }
        for h in WorkerHeartbeat.objects.all()
    ]
    present = {row["queue"] for row in workers}
    workers += [
        {"queue": q, "fresh": False, "seen_at": None, "lag_seconds": None}
        for q in settings.OPERATION_QUEUES
        if q not in present
    ]
    try:
        service_snapshot = cache.get("operations:service-snapshot")
    except Exception:
        service_snapshot = None
    account_rows = []
    for account in accounts:
        control, _ = AccountControl.objects.get_or_create(account=account)
        account_rows.append({
            "id": account.pk,
            "exchange": account.exchange.code,
            "label": account.label,
            "status": account.status,
            "paused": control.paused,
            "reason": control.reason,
            "version": control.version,
            "last_reconciled_at": control.last_reconciled_at,
            "last_sync_at": account.last_sync_at,
        })
    return {
        "accounts": account_rows,
        "workers": workers,
        "issues": RecoveryIssue.objects.filter(account__owner=user, resolved=False).select_related("account"),
        "external": ExternalObservation.objects.filter(account__owner=user)[:50],
        "service_snapshot": service_snapshot,
    }


@login_required
@never_cache
@require_GET
def center(request):
    return render(
        request, "operations/center.html", {**health_context(request.user), "nav": "operations"}
    )


@transaction.atomic
def set_paused(user, account_id, *, paused, version):
    account = UserExchangeAccount.objects.get(pk=account_id, owner=user)
    control, _ = AccountControl.objects.get_or_create(account=account)
    control = AccountControl.objects.select_for_update().get(pk=control.pk)
    if control.version != version:
        raise ValidationError("وضعیت تغییر کرده است؛ صفحه را تازه کنید.")
    if not paused:
        if RecoveryIssue.objects.filter(account=account, resolved=False).exists():
            raise ValidationError("ابتدا اختلاف‌ها و dead-letter را رفع و تطبیق را اجرا کنید.")
        if (
            not control.last_reconciled_at
            or control.last_reconciled_at < timezone.now() - timedelta(minutes=5)
        ):
            raise ValidationError("ابتدا تطبیق حساب را اجرا کنید.")
    control.paused = paused
    control.reason = "operator_pause" if paused else ""
    control.version += 1
    control.save()
    record_audit(
        "operations.pause" if paused else "operations.resume",
        user=user,
        metadata={"account_id": account.pk},
    )
    return control


@login_required
@require_POST
def control(request, pk):
    get_object_or_404(UserExchangeAccount, owner=request.user, pk=pk)
    try:
        action = request.POST.get("action")
        if action == "reconcile":
            from .tasks import reconcile_one

            reconcile_one.apply_async(args=[pk], queue="maintenance")
            messages.success(request, "تطبیق در صف قرار گرفت.")
        elif action in {"pause", "resume"}:
            if request.POST.get("confirmed") != "on":
                raise ValidationError("تأیید صریح تغییر ورود جدید لازم است.")
            set_paused(
                request.user,
                pk,
                paused=action == "pause",
                version=int(request.POST.get("version", "0")),
            )
            messages.success(request, "وضعیت اجرای جدید تغییر کرد؛ خروج‌های حفاظتی ادامه دارند.")
        else:
            raise ValidationError("عملیات نامعتبر است.")
    except (ValidationError, ValueError):
        messages.error(
            request, "تغییر انجام نشد؛ نسخه وضعیت، تطبیق اخیر و اختلاف‌های باز را بررسی کنید."
        )
    return redirect("operations")


@session_api_required
@never_cache
@require_GET
def api_health(request):
    data = health_context(request.user)
    return JsonResponse(
        {
            "workers": data["workers"],
            "accounts": data["accounts"],
            "unresolved_issues": [
                {
                    "id": item.pk,
                    "account_id": item.account_id,
                    "account": item.account.label,
                    "code": item.code,
                    "key": item.key,
                    "created_at": item.created_at,
                }
                for item in data["issues"][:100]
            ],
            "external_observations": data["external"].count(),
            "live_execution": settings.LIVE_TRADING_ENABLED,
            "service_snapshot": data["service_snapshot"],
        }
    )


@session_api_required
@require_POST
def api_control(request, pk):
    account = get_object_or_404(
        UserExchangeAccount.objects.filter(owner=request.user, environment="live"), pk=pk
    )
    try:
        import json
        body = json.loads(request.body or b"{}") if request.content_type == "application/json" else request.POST
        action = str(body.get("action", ""))
        if action == "reconcile":
            from .tasks import reconcile_one
            reconcile_one.apply_async(args=[account.pk], queue="maintenance")
            return JsonResponse({"queued": True}, status=202)
        if action not in {"pause", "resume"}:
            raise ValidationError("عملیات نامعتبر است.")
        if body.get("confirmed") is not True and str(body.get("confirmed", "")).lower() not in {"on", "true", "1"}:
            raise ValidationError("تأیید صریح تغییر وضعیت لازم است.")
        control = set_paused(
            request.user,
            account.pk,
            paused=action == "pause",
            version=int(body.get("version", 0)),
        )
        return JsonResponse({
            "account_id": account.pk,
            "paused": control.paused,
            "version": control.version,
            "last_reconciled_at": control.last_reconciled_at,
        })
    except (ValidationError, ValueError, TypeError) as error:
        return JsonResponse({"error": getattr(error, "messages", [str(error)])}, status=400)


@login_required
@require_POST
@transaction.atomic
def resolve_dead_letter(request, pk):
    from apps.trading.execution import consume_receipt
    from apps.trading.models import (
        CapitalReservation,
        ExecutionOutbox,
        Order,
        Trade,
        TradeEvent,
    )

    from .provider import lookup

    info = get_object_or_404(
        ExecutionOutbox.objects.select_related("order"), pk=pk, order__trade__owner=request.user
    )
    account = info.order.account
    if account.environment != "paper" or account.exchange.adapter_code != "simulator":
        return JsonResponse({"error": "paper_only"}, status=400)
    control, _ = AccountControl.objects.get_or_create(account=account)
    AccountControl.objects.select_for_update().get(pk=control.pk)
    trade = Trade.objects.select_for_update().get(pk=info.order.trade_id)
    order = Order.objects.select_for_update().get(pk=info.order_id)
    box = ExecutionOutbox.objects.select_for_update().get(pk=pk)
    if not box.dead_letter or str(box.fence) != request.POST.get("fence"):
        return JsonResponse({"error": "stale_or_not_dead_letter"}, status=409)
    receipt = lookup(order)
    if receipt:
        consume_receipt(box.pk, receipt)
    elif order.filled_quantity == 0 and box.state in {"uncertain", "error"}:
        order.state, trade.state = "failed", "failed"
        order.save(update_fields=("state", "updated_at"))
        trade.save(update_fields=("state", "updated_at"))
        box.state, box.dead_letter = "done", False
        box.fence += 1
        box.last_error_code = "operator_discarded"
        box.save()
        CapitalReservation.objects.filter(trade=trade).update(active=False)
        TradeEvent.objects.create(trade=trade, event_type="DEAD_LETTER_DISCARDED")
    else:
        return JsonResponse({"error": "reconciliation_required"}, status=409)
    RecoveryIssue.objects.filter(account=account, key=f"outbox:{pk}").update(resolved=True)
    record_audit("operations.dead_letter_resolved", user=request.user, metadata={"outbox_id": pk})
    messages.success(
        request, "نتیجه از دفتر شبیه‌ساز بررسی شد؛ تطبیق و ادامهٔ حساب را جداگانه اجرا کنید."
    )
    return redirect("operations")



@session_api_required
@never_cache
@require_http_methods(["GET", "POST", "PATCH"])
def api_external_management(request, pk):
    from .external_management import (
        adopt_or_update,
        normalize_external,
        serialize_management,
        set_state,
    )

    observation = get_object_or_404(
        ExternalObservation.objects.select_related(
            "account", "account__exchange"
        ),
        pk=pk,
        account__owner=request.user,
        account__status__in=("connected", "restricted"),
    )
    management = getattr(observation, "management", None)
    if request.method == "GET":
        return JsonResponse(
            {
                "external": normalize_external(observation),
                "management": serialize_management(management),
            }
        )
    if not has_recent_step_up(request):
        return JsonResponse(
            {
                "error": "step_up_required",
                "verify_url": "/cryptosniper/settings/security/step-up/",
            },
            status=403,
        )
    try:
        import json

        body = (
            json.loads(request.body or b"{}")
            if request.content_type == "application/json"
            else request.POST
        )
        action = str(body.get("action", "save"))
        if action in {"pause", "resume"}:
            management = set_state(request.user, observation.pk, action)
        elif action == "save":
            if body.get("confirmed") is not True:
                raise ValidationError("تأیید صریح مدیریت معامله لازم است.")
            management = adopt_or_update(request.user, observation.pk, body)
        else:
            raise ValidationError("عملیات مدیریت معامله معتبر نیست.")
        return JsonResponse(
            {
                "external": normalize_external(observation),
                "management": serialize_management(management),
            }
        )
    except (ValidationError, ValueError, TypeError) as error:
        return JsonResponse(
            {"error": getattr(error, "messages", [str(error)])},
            status=400,
        )
