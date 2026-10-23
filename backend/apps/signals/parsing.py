"""Stage07 extraction diagnostics and review-only Inbox integration."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.exchanges.models import ExchangeMarket, UserExchangeAccount

from .models import Signal, SignalTarget
from .parser import PARSER_VERSION, extract
from .services import _revision, _validate_structure


def _unique_market_match(owner, pair):
    if not pair:
        return None, None
    accounts = list(
        UserExchangeAccount.objects.for_user(owner)
        .filter(
            status__in=("connected", "restricted"),
            permissions__can_read=True,
            environment="live",
        )
        .select_related("exchange")
    )
    matches = []
    for account in accounts:
        market = (
            ExchangeMarket.objects.filter(
                exchange=account.exchange,
                symbol=pair,
                active=True,
            )
            .order_by("market_type", "pk")
            .first()
        )
        if market:
            matches.append((account, market))
    return matches[0] if len(matches) == 1 else (None, None)


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
    return {
        **parsed,
        "technical_confidence": confidence,
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

    account, market = _unique_market_match(owner, parsed.get("pair"))
    can_materialize = (
        account
        and market
        and parsed.get("side")
        and parsed.get("entry")
        and parsed.get("stop_loss")
        and parsed.get("execution_targets")
        and not parsed.get("entry_range")
        and not parsed.get("futures_mentioned")
    )
    if can_materialize:
        try:
            data = {
                "account_id": account.pk,
                "market_id": market.pk,
                "side": parsed["side"],
                "entry_price": Decimal(parsed["entry"]),
                "stop_loss": Decimal(parsed["stop_loss"]),
                "targets": [
                    {"price": Decimal(value)}
                    for value in parsed["execution_targets"]
                ],
            }
            _, _, targets = _validate_structure(owner, data)
            signal.exchange_account = account
            signal.market = market
            signal.side = data["side"]
            signal.entry_price = data["entry_price"]
            signal.stop_loss = data["stop_loss"]
            signal.status = Signal.Status.PARSED
            signal.review_reason = "استخراج کامل است؛ قبل از تأیید نهایی مقادیر را مرور کنید."
            signal.revision += 1
            signal.save()
            signal.targets.all().delete()
            SignalTarget.objects.bulk_create(
                [
                    SignalTarget(
                        signal=signal,
                        position=index + 1,
                        price=price,
                        share_percent=share,
                    )
                    for index, (price, share) in enumerate(targets)
                ]
            )
            _revision(signal, owner=owner, reason="تحلیل ساختاری کامل با بازار یکتا")
            return signal
        except ValidationError as error:
            parsed["materialize_warning"] = str(error)

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
    _revision(signal, owner=owner, reason="تحلیل ساختاری نیازمند تأیید انسان")
    return signal
