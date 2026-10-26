"""Owner-scoped management reads and explicit, versioned sensitive writes."""

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from apps.accounts.audit import record_audit
from apps.accounts.security import has_recent_step_up, session_api_required
from apps.exchanges.models import LiveSpotOrder, UserExchangeAccount
from apps.exchanges.reconciliation import TERMINAL, reconcile_order
from apps.operations.models import ExternalObservation, ExternalTradePolicy, ManagedSpotPosition

from .external_management import apply_external_policy
from .external_utils import normalized_external
from .live_management import enabled


def position_payload(position):
    return {
        "id": position.pk,
        "version": position.version,
        "state": position.state,
        "acquired": str(position.acquired),
        "exited": str(position.exited),
        "remaining": str(position.remaining),
        "effective_stop": str(position.effective_stop),
        "high_water": str(position.high_water) if position.high_water else None,
        "paused": position.paused,
        "break_even_applied": position.break_even_applied,
        "trailing_active": position.trailing_active,
        "error_code": position.error_code,
        "last_price_at": position.last_price_at,
        "last_checked_at": position.last_checked_at,
        "snapshot": position.snapshot,
        "execution_enabled": bool(enabled() and not position.paused),
        "exits": [
            {
                "id": a.order_id,
                "reason": a.reason,
                "state": a.order.state,
                "amount": str(a.order.amount),
                "filled": str(a.order.filled_amount),
                "price": str(a.order.average_price or a.order.price),
                "time": a.created_at,
            }
            for a in position.exits.select_related("order").order_by("sequence")
        ],
    }


def _body(request):
    from apps.core.react_views import _body as read_body

    body = read_body(request)
    if not has_recent_step_up(request):
        raise PermissionError
    return body


@session_api_required
@never_cache
@require_http_methods(["GET", "POST"])
def api_external_management(request, pk):
    item = get_object_or_404(
        ExternalObservation.objects.select_related("account__exchange"),
        pk=pk,
        account__owner=request.user,
    )
    policy = ExternalTradePolicy.objects.filter(observation=item).first()
    if request.method == "GET":
        return JsonResponse(
            {
                "observation": {
                    k: str(v) if isinstance(v, Decimal) else v
                    for k, v in normalized_external(item).items()
                },
                "policy_version": policy.version if policy else None,
                "position": position_payload(policy.managed_position)
                if policy and hasattr(policy, "managed_position")
                else None,
                "execution_enabled": enabled(),
            }
        )
    try:
        data = _body(request)
        if data.get("confirmed") is not True:
            raise ValidationError("پذیرش صریح حجم باقی‌مانده لازم است.")
        policy = apply_external_policy(request.user, pk, data)
        return JsonResponse({"position": position_payload(policy.managed_position)}, status=201)
    except PermissionError:
        return JsonResponse({"error": "step_up_required"}, status=403)
    except (ValidationError, ValueError, TypeError) as error:
        return JsonResponse({"error": getattr(error, "messages", [str(error)])}, status=400)


@transaction.atomic
def change_position(owner, pk, body):
    original = ManagedSpotPosition.objects.get(pk=pk, account__owner=owner)
    UserExchangeAccount.objects.select_for_update().get(pk=original.account_id)
    p = ManagedSpotPosition.objects.select_for_update().select_related("market").get(pk=pk)
    if body.get("confirmed") is not True or int(body.get("version", 0)) != p.version:
        raise ValidationError("تأیید صریح و نسخهٔ تازه لازم است.")
    action = body.get("action")
    if action in {"pause", "resume"}:
        p.paused = action == "pause"
        if action == "resume":
            if not enabled():
                raise ValidationError("اجرای مدیریت خروج روی سرور خاموش است.")
            # Acknowledging a proven failed (not uncertain) attempt permits a new intent.
            if not p.exits.exclude(order__state__in=TERMINAL).exists():
                p.exit_sequence += 1
    elif action == "update":
        if p.exits.exclude(order__state__in=TERMINAL).exists():
            raise ValidationError("سفارش خروج در جریان است؛ ابتدا نتیجه آن باید مشخص شود.")
        snapshot = dict(p.snapshot)
        stop = Decimal(str(body["stop_loss"]))
        prices = [
            Decimal(str(body[k])) for k in ("tp1", "tp2", "tp3") if body.get(k) not in (None, "")
        ]
        if (
            not prices
            or prices != sorted(set(prices))
            or any(not v.is_finite() or v <= Decimal(snapshot["entry_price"]) for v in prices)
        ):
            raise ValidationError("TPهای صعودی بالاتر از Entry لازم‌اند.")
        if (
            not stop.is_finite()
            or stop <= 0
            or any(v % p.market.price_step for v in [stop, *prices])
        ):
            raise ValidationError("SL و قیمت‌های بازار معتبر نیستند.")
        if stop < p.effective_stop:
            raise ValidationError("حد ضرر حفاظت‌شده را نمی‌توان ضعیف‌تر کرد.")
        trigger = str(body.get("trailing_trigger", snapshot.get("trailing_trigger", "tp1")))
        distance = Decimal(
            str(body.get("trailing_distance_percent", snapshot.get("trailing_distance_percent", 1)))
        )
        if (
            trigger not in [f"tp{i + 1}" for i in range(len(prices))]
            or not distance.is_finite()
            or distance != distance.to_integral_value()
            or not 1 <= distance <= 99
        ):
            raise ValidationError("شروع و فاصله صحیح Trailing معتبر نیستند.")
        shares = [Decimal(v) for v in snapshot.get("tp_distribution", [10, 10, 80])]
        shares += [Decimal(0)] * (len(prices) - len(shares))
        shares = shares[: len(prices) - 1] + [sum(shares[len(prices) - 1 :])]
        snapshot.update(
            stop_loss=str(stop),
            targets=[
                {"price": str(v), "share_percent": str(shares[i])} for i, v in enumerate(prices)
            ],
            trailing_trigger=trigger,
            trailing_distance_percent=str(distance),
        )
        for field in ("trailing_sl", "percentage_trailing"):
            if field in body:
                if not isinstance(body[field], bool):
                    raise ValidationError("تیک فعال‌سازی معتبر نیست.")
                snapshot[field] = body[field]
        if body.get("remaining_amount") not in (None, ""):
            remaining = Decimal(str(body["remaining_amount"]))
            if (
                not remaining.is_finite()
                or remaining <= 0
                or remaining > p.remaining
                or remaining % p.market.amount_step
            ):
                raise ValidationError("تنها کاهشِ صحیحِ حجم باقی‌مانده مجاز است.")
            latest = (
                p.account.balance_snapshots.filter(asset=p.market.base_asset, wallet_scope="spot")
                .order_by("-captured_at")
                .first()
            )
            if (
                not latest
                or latest.captured_at < timezone.now() - timedelta(minutes=2)
                or remaining > latest.free_balance
            ):
                raise ValidationError("حجم باقی‌مانده با موجودی آزاد تازه تأیید نمی‌شود.")
            p.acquired = p.exited + remaining
            if p.entry_order_id:
                p.inventory_cap = p.acquired
        p.snapshot, p.effective_stop = snapshot, stop
    else:
        raise ValidationError("عملیات معتبر نیست.")
    p.version += 1
    p.save()
    record_audit(
        "live.management_changed",
        user=owner,
        metadata={"position_id": p.pk, "action": action, "version": p.version},
    )
    return p


@session_api_required
@never_cache
@require_http_methods(["GET", "POST"])
def api_position(request, pk):
    p = get_object_or_404(ManagedSpotPosition, pk=pk, account__owner=request.user)
    if request.method == "GET":
        return JsonResponse({"position": position_payload(p)})
    try:
        p = change_position(request.user, pk, _body(request))
        return JsonResponse({"position": position_payload(p)})
    except PermissionError:
        return JsonResponse({"error": "step_up_required"}, status=403)
    except (
        ValidationError,
        InvalidOperation,
        ValueError,
        TypeError,
        KeyError,
        ZeroDivisionError,
    ) as error:
        return JsonResponse({"error": getattr(error, "messages", [str(error)])}, status=400)


@session_api_required
@never_cache
@require_http_methods(["POST"])
def api_reconcile_order(request, pk):
    order = get_object_or_404(LiveSpotOrder, pk=pk, owner=request.user)
    try:
        body = _body(request)
        cancel = body.get("cancel") is True
        result = reconcile_order(
            order.pk, external_id=str(body.get("external_id") or "")[:120], cancel=cancel
        )
        record_audit(
            "live.order_reconciled",
            user=request.user,
            metadata={"order_id": order.pk, "cancel_requested": cancel, "result": result},
        )
        return JsonResponse({"status": result})
    except PermissionError:
        return JsonResponse({"error": "step_up_required"}, status=403)
    except (ValidationError, ValueError, TypeError) as error:
        return JsonResponse({"error": getattr(error, "messages", [str(error)])}, status=400)


@session_api_required
@never_cache
@require_http_methods(["POST"])
@transaction.atomic
def api_enable_entry(request, pk):
    order = get_object_or_404(
        LiveSpotOrder.objects.select_related("source_plan", "market", "account"),
        pk=pk,
        owner=request.user,
    )
    try:
        body = _body(request)
        UserExchangeAccount.objects.select_for_update().get(pk=order.account_id)
        if (
            body.get("confirmed") is not True
            or not order.source_plan
            or order.side != "buy"
            or order.state not in {"filled", "cancelled"}
        ):
            raise ValidationError("رسید نهایی ورود و تأیید حجم باقی‌مانده لازم است.")
        if ManagedSpotPosition.objects.filter(entry_order=order).exists():
            raise ValidationError("مدیریت قبلاً ثبت شده است؛ دوباره بارگذاری کنید.")
        amount = Decimal(str(body["remaining_amount"]))
        latest = (
            order.account.balance_snapshots.filter(
                asset=order.market.base_asset, wallet_scope="spot"
            )
            .order_by("-captured_at")
            .first()
        )
        allocated = sum(
            (
                p.remaining
                for p in ManagedSpotPosition.objects.filter(
                    account=order.account, market__base_asset=order.market.base_asset
                ).exclude(state__in=("closed", "cancelled"))
            ),
            Decimal(0),
        )
        if (
            not amount.is_finite()
            or not 0 < amount <= order.filled_amount
            or amount % order.market.amount_step
            or not latest
            or latest.captured_at < timezone.now() - timedelta(minutes=2)
            or amount > latest.free_balance - allocated
        ):
            raise ValidationError("حجم با اجرای ورود و سهم آزاد تازه هم‌خوان نیست.")
        from .live_management import create_entry_position

        p = create_entry_position(order, order.source_plan.approved_snapshot)
        p.acquired = p.inventory_cap = amount
        p.state = "active"
        p.save()
        record_audit(
            "live.entry_management_enabled",
            user=request.user,
            metadata={"position_id": p.pk, "remaining": str(amount)},
        )
        return JsonResponse({"position": position_payload(p)}, status=201)
    except PermissionError:
        return JsonResponse({"error": "step_up_required"}, status=403)
    except (
        ValidationError,
        InvalidOperation,
        ValueError,
        TypeError,
        KeyError,
        ZeroDivisionError,
    ) as error:
        return JsonResponse({"error": getattr(error, "messages", [str(error)])}, status=400)
