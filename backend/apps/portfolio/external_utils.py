from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.utils.dateparse import parse_datetime


def _decimal(value):
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def _symbol(value):
    text = str(value or "").upper().replace("_", "").replace("-", "")
    if "/" in text:
        return text
    for quote in ("USDT", "USDC", "BTC", "ETH", "IRT", "RLS"):
        if text.endswith(quote) and len(text) > len(quote):
            return f"{text[: -len(quote)]}/{quote}"
    return text


def _time(value, fallback):
    if value is None or value == "":
        return fallback
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value, UTC)
    try:
        number = int(value)
        if number > 10_000_000_000:
            number /= 1000
        return datetime.fromtimestamp(number, tz=UTC)
    except (ValueError, TypeError, OSError, OverflowError):
        parsed = parse_datetime(str(value))
        return parsed or fallback


def normalized_external(item):
    payload = item.payload if isinstance(item.payload, dict) else {}
    symbol = _symbol(payload.get("symbol"))
    side = str(payload.get("side", "")).lower()
    if not side and "isBuyer" in payload:
        side = "buy" if payload.get("isBuyer") else "sell"
    entry = next(
        (
            _decimal(payload.get(key))
            for key in ("average_price", "avgPrice", "averagePrice", "price")
            if _decimal(payload.get(key)) is not None
        ),
        None,
    )
    amount = next(
        (
            _decimal(payload.get(key))
            for key in (
                "filled_amount",
                "executedQty",
                "matchedAmount",
                "dealVolume",
                "qty",
                "quantity",
                "amount",
                "origQty",
            )
            if _decimal(payload.get(key)) is not None
        ),
        None,
    )
    raw_status = str(payload.get("status", "")).lower()
    if not raw_status and item.kind in {"fill", "history"}:
        raw_status = "filled"
    labels = {
        "new": "باز",
        "open": "باز",
        "active": "باز",
        "partial": "بخشی اجرا شده",
        "partially_filled": "بخشی اجرا شده",
        "filled": "تکمیل‌شده",
        "done": "تکمیل‌شده",
        "completed": "تکمیل‌شده",
        "cancelled": "لغوشده",
        "canceled": "لغوشده",
    }
    status_label = labels.get(raw_status, raw_status or "ثبت‌شده")
    exact = _time(
        next(
            (
                payload.get(key)
                for key in (
                    "created_at",
                    "time",
                    "create_time",
                    "ctime",
                    "transactTime",
                    "updateTime",
                )
                if payload.get(key) not in {None, ""}
            ),
            None,
        ),
        item.observed_at,
    )
    confirmed_fill = any(
        _decimal(payload.get(k)) is not None and _decimal(payload.get(k)) > 0
        for k in ("filled_amount", "executedQty", "matchedAmount", "dealVolume", "qty", "quantity")
    )
    manageable = (
        (confirmed_fill or raw_status in {"filled", "done", "completed"})
        and side == "buy"
        and amount is not None
        and amount > 0
        and (
            item.kind in {"fill", "history"}
            or raw_status in {"partial", "partially_filled", "filled", "done", "completed"}
        )
    )
    return {
        "symbol": symbol,
        "side": side,
        "side_label": "Long / خرید" if side == "buy" else ("فروش" if side == "sell" else "نامشخص"),
        "entry": entry,
        "amount": amount,
        "status": raw_status,
        "status_label": status_label,
        "exact_time": exact,
        "manageable": manageable,
    }
