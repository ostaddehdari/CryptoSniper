"""Deterministic trailing math; Short is math-only until margin borrow/repay is supported."""

from decimal import Decimal

from django.core.exceptions import ValidationError


def percentage_stop(*, side, high=None, low=None, distance):
    try:
        d = Decimal(str(distance))
        if not d.is_finite() or not Decimal("0") < d < Decimal("100"):
            raise ValueError("distance")
        multiplier = d / Decimal("100")
        if side == "long":
            reference = Decimal(str(high))
            stop = reference * (Decimal("1") - multiplier)
        elif side == "short":
            reference = Decimal(str(low))
            stop = reference * (Decimal("1") + multiplier)
        else:
            raise ValueError("side")
        if not reference.is_finite() or reference <= 0:
            raise ValueError("reference")
        return stop
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise ValidationError("قیمت، جهت یا فاصله trailing معتبر نیست.") from exc


def monotonic_stop(side, current, proposed):
    current = Decimal(str(current))
    proposed = Decimal(str(proposed))
    if not current.is_finite() or not proposed.is_finite() or current <= 0 or proposed <= 0:
        raise ValidationError("Stop محدود و مثبت لازم است.")
    if side == "long":
        return max(current, proposed)
    if side == "short":
        return min(current, proposed)
    raise ValidationError("جهت trailing نامعتبر است.")
