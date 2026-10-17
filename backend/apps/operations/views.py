"""Owner-scoped operations: stop new entries; protective exits keep running."""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.audit import record_audit
from apps.accounts.security import session_api_required
from apps.exchanges.models import UserExchangeAccount
from apps.trading.models import ExecutionOutbox, TradeProtection

from .models import AccountControl, ExternalObservation, RecoveryIssue, WorkerHeartbeat


def health_context(user):
    accounts = UserExchangeAccount.objects.filter(owner=user).select_related(
        "exchange", "accountcontrol"
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
    from django.conf import settings

    present = {row["queue"] for row in workers}
    workers += [
        {"queue": q, "fresh": False, "seen_at": None, "lag_seconds": None}
        for q in settings.OPERATION_QUEUES
        if q not in present
    ]
    oldest = (
        ExecutionOutbox.objects.filter(order__trade__owner=user)
        .exclude(state="done")
        .order_by("created_at")
        .first()
    )
    protections = TradeProtection.objects.filter(
        trade__owner=user, trade__state__in=["open", "partially_filled"]
    )
    feed_lags = [
        (timezone.now() - p.last_tick_at).total_seconds() for p in protections if p.last_tick_at
    ]
    return {
        "accounts": accounts,
        "workers": workers,
        "oldest_pending_seconds": int((timezone.now() - oldest.created_at).total_seconds())
        if oldest
        else 0,
        "feed_lag_seconds": int(max(feed_lags)) if feed_lags else None,
        "issues": RecoveryIssue.objects.filter(account__owner=user, resolved=False).select_related(
            "account"
        ),
        "dead_letters": ExecutionOutbox.objects.filter(
            order__trade__owner=user, dead_letter=True
        ).exclude(state="done"),
        "external": ExternalObservation.objects.filter(account__owner=user)[:50],
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
            "oldest_pending_seconds": data["oldest_pending_seconds"],
            "feed_lag_seconds": data["feed_lag_seconds"],
            "unresolved_issues": data["issues"].count(),
            "live_execution": False,
        }
    )
