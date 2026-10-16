"""Atomic draft/ready lifecycle; no order API or exchange adapter is invoked."""

import hashlib
import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .calculations import build_preview
from .models import TradePlan


def _normalized(data):
    return {
        name: (
            item.pk
            if name in {"account", "market"}
            else str(item)
            if item is not None and hasattr(item, "as_tuple")
            else item
        )
        for name, item in data.items()
        if name != "client_token"
    }


def _hash(data):
    text = json.dumps(_normalized(data), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


@transaction.atomic
def create_draft(owner, data):
    token = data["client_token"]
    digest = _hash(data)
    found = TradePlan.objects.select_for_update().filter(owner=owner, client_token=token).first()
    if found:
        if found.preview.get("form_digest") != digest:
            raise ValidationError("شناسه فرم قبلاً با اطلاعات دیگری استفاده شده؛ فرم جدید بسازید.")
        return found, False
    preview = build_preview(data)
    preview["form_digest"] = digest
    plan = TradePlan.objects.create(
        owner=owner,
        exchange_account=data["account"],
        market=data["market"],
        client_token=token,
        source="manual",
        side=data["side"],
        entry_price=data["entry_price"],
        stop_loss=data["stop_loss"],
        tp1=data["tp1"],
        tp2=data.get("tp2"),
        tp3=data.get("tp3"),
        capital=data["capital"],
        leverage=data["leverage"],
        trailing_sl=data.get("trailing_sl", False),
        percentage_trailing=data.get("percentage_trailing", False),
        trailing_distance=data["trailing_distance"],
        preview=preview,
    )
    return plan, True


@transaction.atomic
def update_draft(plan, data, expected_revision):
    locked = TradePlan.objects.select_for_update().get(pk=plan.pk, owner=plan.owner)
    if locked.status != TradePlan.Status.DRAFT:
        raise ValidationError("برنامه تأییدشده قابل ویرایش نیست؛ طرح جدید بسازید.")
    if locked.revision != expected_revision:
        raise ValidationError("نسخه فرم قدیمی است؛ صفحه را تازه‌سازی کنید.")
    payload = build_preview(data)
    payload["form_digest"] = _hash(data)
    locked.exchange_account = data["account"]
    locked.market = data["market"]
    for name in (
        "side",
        "entry_price",
        "stop_loss",
        "tp1",
        "tp2",
        "tp3",
        "capital",
        "leverage",
        "trailing_sl",
        "percentage_trailing",
        "trailing_distance",
    ):
        setattr(locked, name, data.get(name))
    locked.preview = payload
    locked.revision += 1
    locked.save()
    return locked


@transaction.atomic
def approve_plan(owner, plan_id, expected_revision):
    plan = TradePlan.objects.select_for_update().get(pk=plan_id, owner=owner)
    if plan.status == TradePlan.Status.READY:
        if plan.revision != expected_revision:
            raise ValidationError("نسخه تأیید شده است؛ صفحه را تازه‌سازی کنید.")
        return plan
    if plan.revision != expected_revision:
        raise ValidationError("طرح در تب دیگری تغییر کرده؛ دوباره بررسی کنید.")
    data = {
        "account": plan.exchange_account,
        "market": plan.market,
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
    }
    # Re-check current market limits and cash, then freeze an independently
    # versioned JSON snapshot. Never silently mutate it due to later preferences.
    verified = build_preview(data)
    verified["form_digest"] = plan.preview.get("form_digest")
    plan.status = TradePlan.Status.READY
    plan.approved_snapshot = dict(verified)
    plan.approved_at = timezone.now()
    plan.save(update_fields=("status", "approved_snapshot", "approved_at", "updated_at"))
    return plan
