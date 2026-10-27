"""Stage07 extraction diagnostics and review-only Inbox integration."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Signal
from .parser import PARSER_VERSION, extract
from .services import _revision


def assess(parsed):
    warnings = []
    for field, message in (
        ("pair", "نماد یکتا یافت نشد یا چند جفت‌ارز وجود دارد."),
        ("side", "جهت سیگنال مشخص یا بدون تعارض نیست."),
        ("entry", "قیمت Entry یکتا نیست؛ بازه ورود به تأیید دستی نیاز دارد."),
        ("stop_loss", "حد ضرر یکتا ثبت نشده است."),
    ):
        if not parsed[field]:
            warnings.append(message)
    if not parsed["all_targets"]:
        warnings.append("هدف سود معتبر یافت نشد.")
    if parsed["futures_mentioned"]:
        warnings.append("متن به Futures/Perpetual اشاره دارد؛ تبدیل ضمنی به Margin ممنوع است.")
    if len(parsed["all_targets"]) > 3:
        warnings.append("اهداف مازاد فقط در اصل استخراج محفوظ‌اند؛ سه هدف نخست قابل اجرا هستند.")
    if parsed["entry"] and parsed["stop_loss"] and parsed["side"] and parsed["execution_targets"]:
        entry = Decimal(parsed["entry"])
        stop = Decimal(parsed["stop_loss"])
        targets = [Decimal(t) for t in parsed["execution_targets"]]
        if parsed["side"] == "long":
            ok = stop < entry and all(t > entry for t in targets)
        else:
            ok = stop > entry and all(t < entry for t in targets)
        if not ok:
            warnings.append("ترتیب Entry/SL/TP با جهت سیگنال ناسازگار است.")
        if len(targets) != len(set(targets)):
            warnings.append("TP تکراری است.")
    coverage = sum(bool(parsed[key]) for key in ("pair", "side", "entry", "stop_loss"))
    coverage += int(bool(parsed["all_targets"]))
    confidence = max(0, (coverage * 20) - (10 * int(parsed["futures_mentioned"])))
    validation = {
        "complete": not any(
            message
            for message in warnings
            if message
            not in {"اهداف مازاد فقط در اصل استخراج محفوظ‌اند؛ سه هدف نخست قابل اجرا هستند."}
        ),
        "blocked": bool(parsed["futures_mentioned"]),
        "issues": warnings,
    }
    band = "high" if confidence >= 80 else "medium" if confidence >= 50 else "low"
    return {
        **parsed,
        "technical_confidence": confidence,
        "confidence_band": band,
        "validation": validation,
        "warnings": warnings,
        "review_required": True,
        "entry_policy": "explicit_user_review_only",
        "trailing_defaults": {
            "trailing_sl": True,
            "percentage_trailing": True,
            "percentage_trigger": "tp1",
            "percentage_distance": "1",
            "exit_policy": "percentage_trailing_only",
        },
    }


@transaction.atomic
def parse_for_review(owner, signal_id):
    signal = (
        Signal.objects.select_for_update()
        .select_related("raw_signal", "source")
        .get(owner=owner, pk=signal_id)
    )
    if signal.source.method != "smart_paste":
        raise ValidationError("Parser قالبی فقط برای Smart Paste فعال است.")
    if signal.status not in {"new", "parsed", "needs_review"}:
        raise ValidationError("سیگنال تأیید یا ردشده دوباره پردازش نمی‌شود.")
    raw = signal.raw_signal
    if signal.parsed_payload.get("last_parsed_raw_revision") == raw.revision_number:
        return signal
    current = raw.revisions.order_by("-version").first()
    parsed = assess(extract(current.text if current else raw.original_text))
    parsed.pop("normalized", None)
    parsed["last_parsed_raw_revision"] = raw.revision_number
    signal.parsed_payload = parsed
    signal.parser_version = PARSER_VERSION
    signal.technical_confidence = parsed["technical_confidence"]
    signal.status = Signal.Status.NEEDS_REVIEW
    signal.review_reason = "لطفاً پیشنهادهای استخراج را با متن اصلی مقایسه و تأیید کنید."
    signal.revision += 1
    signal.save(
        update_fields=(
            "parsed_payload",
            "parser_version",
            "technical_confidence",
            "status",
            "review_reason",
            "revision",
            "updated_at",
        )
    )
    _revision(signal, owner=owner, reason="تحلیل قالبی نیازمند تأیید انسان")
    return signal
