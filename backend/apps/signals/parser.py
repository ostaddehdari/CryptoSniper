"""Deterministic Stage07 rule parser: extraction metadata, never a trade decision."""

import re
from decimal import Decimal, InvalidOperation

from .normalization import normalize

PARSER_VERSION = "rules-v2"
PAIR = re.compile(r"(?<![A-Z0-9])(?:#)?([A-Z]{2,12})\s*[/_-]\s*([A-Z]{2,12})(?![A-Z0-9])", re.I)
HASHTAG = re.compile(r"(?<!\w)#([A-Z]{2,12})(USDT|USD)\b", re.I)
URL = re.compile(r"\b(?:https?://|t\.me/)\S+", re.I)
SIDE_LONG = re.compile(r"\b(LONG|BUY)\b|\b(خرید|لانگ)\b", re.I)
SIDE_SHORT = re.compile(r"\b(SHORT|SELL)\b|\b(فروش|شورت)\b", re.I)
FUTURES = re.compile(r"\b(FUTURES?|PERPETUAL|PERP)\b|\b(فیوچرز|دائمی)\b", re.I)
ENTRY = re.compile(
    r"\b(?:ENTRY(?:\s+ZONE|\s+PRICE)?|ENTER|BUY\s+ZONE)\b|(?:ورود|نقطه\s+ورود)", re.I
)
STOP = re.compile(r"\b(?:STOP\s*LOSS|STOPLOSS|SL)\b|(?:حد\s*ضرر|استاپ)", re.I)
TARGET = re.compile(
    r"\b(?:TARGETS?\s*\d*|TAKE\s*PROFIT|TP\s*\d*)\b|(?:اهداف?|هدف\s*\d*|تارگت\s*\d*)", re.I
)
LEVERAGE = re.compile(
    r"(?:\bLEV(?:ERAGE)?\b|اهرم)\s*[:=]?\s*(?:X\s*)?([0-9]+(?:[.,][0-9]+)?)\s*X?", re.I
)
ROW_NUMBERS = re.compile(r"(?<![A-Z0-9])\d+(?:[.,]\d+)*(?![A-Z0-9])")
THOUSANDS_OR_DECIMAL = re.compile(r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\Z")


def _decimal(text):
    # A comma with two trailing digits might be a decimal separator; never turn
    # 1,25 into 125. Only unambiguous thousands grouping is accepted.
    if not THOUSANDS_OR_DECIMAL.fullmatch(text):
        return None
    try:
        value = Decimal(text.replace(",", ""))
        if not value.is_finite() or value <= 0:
            return None
        return format(value, "f")
    except (InvalidOperation, ValueError):
        return None


def _row_prices(line):
    # Strip hashtags/pairs and label ordinal such as TP1, then extract prices.
    stripped = PAIR.sub(" ", line)
    stripped = re.sub(r"^\s*(?:\d+[.)-]|[-•])\s+", " ", stripped)
    stripped = re.sub(r"(?i)\b(?:TP|TARGET|هدف|تارگت)\s*\d+(?!\d)", " ", stripped)
    stripped = re.sub(r"(?i)\b(?:LEV(?:ERAGE)?|اهرم)\s*[:=]?\s*\d+(?:\.\d+)?\s*X?", " ", stripped)
    return [v for x in ROW_NUMBERS.findall(stripped) if (v := _decimal(x))]


def extract(raw: str) -> dict:
    cleaned = normalize(raw)
    searchable = URL.sub(" ", cleaned)
    pairs = []
    for base, quote in PAIR.findall(searchable):
        pair = f"{base.upper()}/{quote.upper()}"
        if pair not in pairs:
            pairs.append(pair)
    for base, quote in HASHTAG.findall(searchable):
        pair = f"{base.upper()}/{quote.upper()}"
        if pair not in pairs:
            pairs.append(pair)
    long = bool(SIDE_LONG.search(searchable))
    short = bool(SIDE_SHORT.search(searchable))
    side = "long" if long and not short else "short" if short and not long else None
    entry_values, stops, targets = [], [], []
    leverage = None
    mode = ""
    for line in searchable.splitlines():
        upper = line.upper()
        if not upper or upper.startswith(("HTTP://", "HTTPS://", "T.ME/")):
            continue
        found_lev = LEVERAGE.search(line)
        if found_lev:
            leverage = _decimal(found_lev.group(1))
        if ENTRY.search(line):
            mode = "entry"
            entry_values.extend(_row_prices(line))
        elif STOP.search(line):
            mode = "sl"
            stops.extend(_row_prices(line))
        elif TARGET.search(line):
            mode = "tp"
            targets.extend(_row_prices(line))
        elif mode == "tp" and re.match(r"^\s*(?:\d+[.)-]|[-•])\s+", line):
            targets.extend(_row_prices(line))
        elif mode == "entry" and re.match(r"^\s*(?:-|TO\b)", line, re.I):
            entry_values.extend(_row_prices(line))
        else:
            mode = ""
    # A labeled range such as 63000 - 65000 is retained as a range, not guessed.
    entry_range = entry_values if len(entry_values) == 2 else None
    entry = entry_values[0] if len(entry_values) == 1 else None
    sl = stops[0] if len(stops) == 1 else None
    return {
        "parser_version": PARSER_VERSION,
        "normalized": cleaned,
        "pairs": pairs,
        "pair": pairs[0] if len(pairs) == 1 else None,
        "side": side,
        "entry": entry,
        "entry_range": entry_range,
        "entry_candidates": entry_values,
        "stop_loss": sl,
        "stop_candidates": stops,
        "all_targets": targets,
        "execution_targets": targets[:3],
        "extra_targets": targets[3:],
        "leverage": leverage,
        "futures_mentioned": bool(FUTURES.search(searchable)),
        "source_hint": "smart_paste",
    }
