"""Transactional Inbox transitions, review evidence, idempotency, and audit."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.audit import record_audit
from apps.exchanges.models import ExchangeMarket, UserExchangeAccount

from .ingestion import ingest
from .models import Signal, SignalRevision, SignalTarget
from .sources import InboundEnvelope


def snapshot(signal):
    return {
        "signal_id": signal.pk,
        "status": signal.status,
        "source_id": signal.source_id,
        "raw_id": signal.raw_signal_id,
        "raw_revision": signal.raw_signal.revision_number,
        "market_id": signal.market_id,
        "account_id": signal.exchange_account_id,
        "side": signal.side,
        "entry": str(signal.entry_price) if signal.entry_price is not None else None,
        "stop_loss": str(signal.stop_loss) if signal.stop_loss is not None else None,
        "targets": [
            {"position": t.position, "price": str(t.price), "share_percent": str(t.share_percent)}
            for t in signal.targets.order_by("position")
        ],
        "technical_confidence": signal.technical_confidence,
        "parser_version": signal.parser_version,
        "parsed_payload": signal.parsed_payload,
        "review_reason": signal.review_reason,
        "revision": signal.revision,
        "execution_enabled": False,
    }


def _revision(signal, *, owner, reason):
    SignalRevision.objects.create(
        signal=signal,
        revision=signal.revision,
        actor=owner,
        reason=reason,
        snapshot=snapshot(signal),
    )


@transaction.atomic
def receive_signal(owner, source, *, text, payload=None, external_id=""):
    raw, created, revised = ingest(
        owner, source, InboundEnvelope(text=text, payload=payload or {}, external_id=external_id)
    )
    signal, created_signal = Signal.objects.get_or_create(
        raw_signal=raw, defaults={"owner": owner, "source": source}
    )
    if created_signal:
        _revision(signal, owner=owner, reason="ورود متن اصلی")
        record_audit(
            "signal.received", user=owner, metadata={"signal_id": signal.pk, "source_id": source.pk}
        )
    elif revised and signal.status in {"new", "parsed", "needs_review"}:
        signal.status = Signal.Status.NEEDS_REVIEW
        signal.review_reason = "نسخه جدیدی از متن اصلی دریافت شده است."
        signal.revision += 1
        signal.save(update_fields=("status", "review_reason", "revision", "updated_at"))
        _revision(signal, owner=owner, reason="نسخه جدید متن ورودی")
    return signal, created, revised


def _validate_structure(owner, data):
    account = (
        UserExchangeAccount.objects.for_user(owner)
        .select_related("exchange")
        .filter(pk=data["account_id"])
        .first()
    )
    if not account or account.status not in {"connected", "restricted"}:
        raise ValidationError("حساب صرافی مجاز و متصل نیست.")
    market = (
        ExchangeMarket.objects.select_related("exchange")
        .filter(pk=data["market_id"], exchange_id=account.exchange_id, active=True)
        .first()
    )
    if not market:
        raise ValidationError("بازار فعالِ متعلق به حساب پیدا نشد.")
    side = data["side"]
    entry, sl = data["entry_price"], data["stop_loss"]
    targets = data["targets"]
    if side not in {"long", "short"} or entry <= 0 or sl <= 0:
        raise ValidationError("قیمت و جهت معامله نامعتبر است.")
    if market.market_type == "spot" and side != "long":
        raise ValidationError("Spot فقط برای Long مجاز است.")
    if market.market_type == "margin" and not account.permissions.get("can_trade_margin"):
        raise ValidationError("مجوز Margin تأیید نشده است.")
    if not 1 <= len(targets) <= 3:
        raise ValidationError("یک تا سه هدف سود لازم است.")
    prices = [t["price"] for t in targets]
    if side == "long" and not (sl < entry and all(t > entry for t in prices)):
        raise ValidationError("برای Long حد ضرر باید پایین‌تر از Entry و هدف‌ها بالاتر باشند.")
    if side == "short" and not (sl > entry and all(t < entry for t in prices)):
        raise ValidationError("برای Short حد ضرر باید بالاتر از Entry و هدف‌ها پایین‌تر باشند.")
    ordered = sorted(set(prices), reverse=side == "short")
    if ordered != prices:
        raise ValidationError("هدف‌ها باید مرتب و غیرتکراری باشند.")
    if market.price_step is None or market.price_step <= 0:
        raise ValidationError("Tick Size بازار هنوز همگام نشده است.")
    for val in [entry, sl, *prices]:
        if val % market.price_step:
            raise ValidationError("قیمت‌ها باید مطابق Tick Size بازار باشند.")
    weights = (
        [Decimal("100")]
        if len(targets) == 1
        else (
            [Decimal("10"), Decimal("90")]
            if len(targets) == 2
            else [Decimal("10"), Decimal("10"), Decimal("80")]
        )
    )
    return account, market, list(zip(prices, weights, strict=True))


@transaction.atomic
def update_parsed(owner, pk, *, expected_revision, data, reason):
    signal = (
        Signal.objects.select_for_update()
        .select_related("raw_signal", "source")
        .get(owner=owner, pk=pk)
    )
    if signal.revision != expected_revision:
        raise ValidationError("نسخه فرم قدیمی است؛ صفحه را تازه کنید.")
    if signal.status not in {"new", "parsed", "needs_review"}:
        raise ValidationError("سیگنال در این وضعیت قابل اصلاح نیست.")
    reason = (reason or "").strip() or "اصلاح فیلدهای سیگنال توسط کاربر"
    account, market, targets = _validate_structure(owner, data)
    signal.exchange_account = account
    signal.market = market
    signal.side = data["side"]
    signal.entry_price = data["entry_price"]
    signal.stop_loss = data["stop_loss"]
    signal.technical_confidence = 100  # completeness of manually reviewed fields ONLY
    signal.parser_version = "manual-review-v1"
    extracted = dict(signal.parsed_payload)
    signal.parsed_payload = {
        "edited_by_owner": True,
        "extraction": extracted if extracted.get("parser_version") else {},
        "trailing_sl": bool(extracted.get("trailing_defaults", {}).get("trailing_sl", False)),
        "percentage_trailing": bool(
            extracted.get("trailing_defaults", {}).get("percentage_trailing", False)
        ),
        "percentage_trigger": "tp1",
        "percentage_distance": "1",
    }
    signal.status = Signal.Status.PARSED
    signal.review_reason = ""
    signal.revision += 1
    signal.full_clean()
    signal.save()
    signal.targets.all().delete()
    SignalTarget.objects.bulk_create(
        [
            SignalTarget(signal=signal, position=i + 1, price=price, share_percent=share)
            for i, (price, share) in enumerate(targets)
        ]
    )
    _revision(signal, owner=owner, reason=reason)
    record_audit(
        "signal.revised", user=owner, metadata={"signal_id": signal.pk, "revision": signal.revision}
    )
    return signal


@transaction.atomic
def transition(owner, pk, *, expected_revision, action, reason=""):
    signal = (
        Signal.objects.select_for_update()
        .select_related("raw_signal", "source")
        .get(owner=owner, pk=pk)
    )
    if signal.revision != expected_revision:
        raise ValidationError("نسخه سیگنال تغییر کرده است؛ صفحه را تازه کنید.")
    if action == "approve":
        if signal.status != Signal.Status.PARSED:
            raise ValidationError("فقط سیگنال کامل و بازبینی‌شده قابل تأیید است.")
        if signal.source.method == "smart_paste" and signal.parsed_payload.get(
            "extraction", {}
        ).get("futures_mentioned"):
            raise ValidationError("سیگنال Futures نباید ضمنی به Spot/Margin تبدیل شود.")
        if not signal.market_id or not signal.exchange_account_id:
            raise ValidationError("بازار یا حساب تأیید نشده است.")
        values = list(signal.targets.order_by("position").values("price"))
        _validate_structure(
            owner,
            {
                "account_id": signal.exchange_account_id,
                "market_id": signal.market_id,
                "side": signal.side,
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "targets": values,
            },
        )
        signal.status = Signal.Status.APPROVED
        signal.approved_snapshot = snapshot(signal)
        signal.approved_snapshot["status"] = Signal.Status.APPROVED
        signal.approved_snapshot["approved_at"] = timezone.now().isoformat()
        signal.review_reason = ""
    elif action == "reject":
        if signal.status not in {"new", "parsed", "needs_review"}:
            raise ValidationError("سیگنال در این وضعیت قابل رد نیست.")
        if not reason or len(reason.strip()) < 3:
            raise ValidationError("علت رد سیگنال را بنویسید.")
        signal.status = Signal.Status.REJECTED
        signal.review_reason = reason.strip()
    elif action == "review":
        if signal.status not in {"new", "parsed"}:
            raise ValidationError("این انتقال وضعیت مجاز نیست.")
        if not reason or len(reason.strip()) < 3:
            raise ValidationError("دلیل بازبینی را بنویسید.")
        signal.status = Signal.Status.NEEDS_REVIEW
        signal.review_reason = reason.strip()
    else:
        # Executed / Failed transitions are reserved for the later trade engine.
        raise ValidationError("این انتقال وضعیت در Stage 06 مجاز نیست.")
    signal.revision += 1
    signal.full_clean()
    signal.save()
    _revision(signal, owner=owner, reason=reason.strip() or "تأیید دستی")
    record_audit(
        "signal." + action,
        user=owner,
        metadata={"signal_id": signal.pk, "revision": signal.revision},
    )
    return signal


@transaction.atomic
def trash_signals(owner, ids):
    ids = {int(pk) for pk in ids if str(pk).isdigit()}
    if not ids:
        return 0
    rows = list(
        Signal.objects.select_for_update()
        .filter(owner=owner, pk__in=ids, trashed_at__isnull=True)
        .values_list("pk", flat=True)
    )
    if not rows:
        return 0
    Signal.objects.filter(pk__in=rows, owner=owner).update(trashed_at=timezone.now())
    record_audit(
        "signal.trashed",
        user=owner,
        metadata={"count": len(rows), "signal_ids": rows[:50]},
    )
    return len(rows)


@transaction.atomic
def restore_signals(owner, ids):
    ids = {int(pk) for pk in ids if str(pk).isdigit()}
    if not ids:
        return 0
    rows = list(
        Signal.objects.select_for_update()
        .filter(owner=owner, pk__in=ids, trashed_at__isnull=False)
        .values_list("pk", flat=True)
    )
    if not rows:
        return 0
    Signal.objects.filter(pk__in=rows, owner=owner).update(trashed_at=None)
    record_audit(
        "signal.restored",
        user=owner,
        metadata={"count": len(rows), "signal_ids": rows[:50]},
    )
    return len(rows)
