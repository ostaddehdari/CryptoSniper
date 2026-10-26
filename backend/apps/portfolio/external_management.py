"""Explicit adoption into the same durable exit ledger as internal orders."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.audit import record_audit
from apps.accounts.models import TradingPreferences
from apps.exchanges.models import LiveSpotOrder, UserExchangeAccount
from apps.operations.models import ExternalObservation, ExternalTradePolicy, ManagedSpotPosition

from .forms import ExternalTradePolicyForm
from .live_management import enabled


def _snapshot(data, owner):
    prefs = TradingPreferences.objects.filter(owner=owner).first()
    shares = [prefs.tp1_percent, prefs.tp2_percent, prefs.tp3_percent] if prefs else [10, 10, 80]
    targets = [data[k] for k in ("tp1", "tp2", "tp3") if data.get(k) is not None]
    distribution = shares[: len(targets)]
    distribution[-1] += sum(shares[len(targets) :])
    return {
        "tp_distribution": [str(v) for v in shares],
        "entry_price": str(data["entry_price"]),
        "stop_loss": str(data["stop_loss"]),
        "targets": [
            {"price": str(price), "share_percent": str(distribution[i])}
            for i, price in enumerate(targets)
        ],
        "trailing_sl": bool(data.get("trailing_sl_enabled")),
        "percentage_trailing": bool(data.get("trailing_enabled")),
        "trailing_trigger": "tp" + str(data["trailing_trigger"]),
        "trailing_distance_percent": str(data["trailing_distance_percent"]),
    }


@transaction.atomic
def apply_external_policy(owner, observation_id, data):
    item = ExternalObservation.objects.select_related("account__exchange").get(
        pk=observation_id, account__owner=owner
    )
    UserExchangeAccount.objects.select_for_update().get(pk=item.account_id)
    item = ExternalObservation.objects.select_for_update().get(pk=item.pk)
    if not enabled():
        raise ValidationError("اجرای Live و مدیریت خروج روی سرور باید مجاز باشند.")
    policy = ExternalTradePolicy.objects.select_for_update().filter(observation=item).first()
    form = ExternalTradePolicyForm(data, item=item, instance=policy)
    if not form.is_valid():
        raise ValidationError(form.errors.as_text())
    data = form.cleaned_data
    if policy and int(data.get("version") or 0) != policy.version:
        raise ValidationError("نسخهٔ شرایط تغییر کرده است؛ دوباره بارگذاری کنید.")
    canonical = str(item.payload.get("orderId") or item.payload.get("order_id") or "")
    if (
        canonical
        and LiveSpotOrder.objects.filter(account=item.account, external_order_id=canonical).exists()
    ):
        raise ValidationError("این سفارش داخلی است؛ دوباره به عنوان خارجی پذیرفته نمی‌شود.")
    reference = canonical or str(
        item.payload.get("tradeId") or item.payload.get("id") or item.external_id
    )
    if (
        len(reference) > 120
        or ManagedSpotPosition.objects.filter(
            account=item.account, source_reference=reference
        ).exists()
    ):
        raise ValidationError("این شناسهٔ اجرا قبلاً به مدیریت واگذار شده یا معتبر نیست.")
    if policy and hasattr(policy, "managed_position"):
        # Existing policies use the versioned condition editor; adoption is one-time.
        raise ValidationError("این مشاهده قبلاً واگذار شده است؛ شرایط معامله را ویرایش کنید.")
    latest = (
        item.account.balance_snapshots.filter(asset=data["market"].base_asset, wallet_scope="spot")
        .order_by("-captured_at")
        .first()
    )
    allocated = sum(
        (
            p.remaining
            for p in ManagedSpotPosition.objects.filter(
                account=item.account, market__base_asset=data["market"].base_asset
            ).exclude(state__in=("closed", "cancelled"))
        ),
        Decimal(0),
    )
    if (
        not latest
        or not timezone.now() - timedelta(minutes=2)
        <= latest.captured_at
        <= timezone.now() + timedelta(seconds=5)
        or latest.free_balance - allocated < data["remaining_amount"]
    ):
        raise ValidationError(
            "حجم آزاد تازه پس از کسر موجودی مدیریت‌شده کافی نیست؛ Sync و بررسی کنید."
        )
    policy = policy or ExternalTradePolicy(observation=item)
    policy.market = data["market"]
    for name in (
        "entry_price",
        "remaining_amount",
        "stop_loss",
        "tp1",
        "tp2",
        "tp3",
        "trailing_enabled",
        "trailing_sl_enabled",
        "trailing_trigger",
        "trailing_distance_percent",
    ):
        setattr(policy, name, data[name])
    policy.effective_stop = data["stop_loss"]
    policy.state = "active"
    policy.version += 1
    policy.save()
    position = ManagedSpotPosition.objects.create(
        account=item.account,
        market=data["market"],
        external_policy=policy,
        source_reference=reference,
        acquired=data["remaining_amount"],
        snapshot=_snapshot(data, owner),
        effective_stop=data["stop_loss"],
        state="active",
    )
    record_audit(
        "external.management_enabled",
        user=owner,
        metadata={"observation_id": item.pk, "policy_id": policy.pk, "position_id": position.pk},
    )
    return policy


def monitor_policy(policy_id):
    policy = ExternalTradePolicy.objects.get(pk=policy_id)
    return (
        "managed_by_position_worker" if hasattr(policy, "managed_position") else "review_required"
    )


def monitor_active_external_trades():
    # Pre-S31 policies require renewed explicit adoption. The unified worker is the sole executor.
    return {
        "legacy_review_required": ExternalTradePolicy.objects.filter(
            state="active", managed_position__isnull=True
        ).count()
    }
