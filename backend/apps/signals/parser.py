"""Deterministic Stage07 rule parser: extraction metadata, never a trade decision."""

import re
from decimal import Decimal, InvalidOperation

from .normalization import normalize

PARSER_VERSION = "rules-v2"
NUMBER = r"((?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?|\.[0-9]+)"
PAIR = re.compile(r"(?<![A-Z0-9])(?:#)?([A-Z]{2,12})\s*[/_-]\s*([A-Z]{2,12})(?![A-Z0-9])", re.I)
COMPACT_PAIR = re.compile(
    r"(?<![A-Z0-9])(?:#|\$)?([A-Z0-9]{2,12})(USDT|USDC|USD|BTC|ETH|IRT|RLS)(?![A-Z0-9])",
    re.I,
)
SIDE_LONG = re.compile(r"\b(LONG|BUY)\b|(?:خرید|لانگ|صعودی)", re.I)
SIDE_SHORT = re.compile(r"\b(SHORT|SELL)\b|(?:فروش|شورت|نزولی)", re.I)
FUTURES = re.compile(r"\b(FUTURES?|PERPETUAL|PERP)\b|\b(فیوچرز|دائمی)\b", re.I)
ENTRY = re.compile(
    r"\b(?:ENTRY(?:\s+(?:ZONE|PRICE|POINT))?|ENTER|BUY\s+ZONE)\b|"
    r"(?:ورودی|ورود|نقطه\s+ورود|محدوده\s+خرید|قیمت\s+ورود)",
    re.I,
)
STOP = re.compile(r"\b(?:STOP\s*LOSS|STOPLOSS|S\s*/\s*L|SL)\b|(?:حد\s*ضرر|استاپ)", re.I)
TARGET = re.compile(
    r"\b(?:TARGETS?|TAKE\s*PROFIT|T\s*/\s*P|TP(?:[1-9]\b|\s+[1-9](?=\s*[:=-]))?)\b|"
    r"(?:اهداف|هدف(?:\s+[1-9](?=\s*[:=-]))?|تارگت(?:\s+[1-9](?=\s*[:=-]))?|سود(?:\s+[1-9](?=\s*[:=-]))?)",
    re.I,
)
LEVERAGE = re.compile(
    r"(?:\bLEV(?:ERAGE)?\b|اهرم)\s*[:=]?\s*(?:X\s*)?([0-9]+(?:[.,][0-9]+)?)\s*X?", re.I
)
ROW_NUMBERS = re.compile(rf"(?<![A-Z0-9]){NUMBER}(?![A-Z0-9])")


def _decimal(text):
    try:
        value = Decimal(text.replace(",", ""))
        if not value.is_finite() or value <= 0:
            return None
        return format(value, "f")
    except (InvalidOperation, ValueError):
        return None


def _labeled_segments(line):
    matches = []
    for kind, pattern in (("entry", ENTRY), ("sl", STOP), ("tp", TARGET)):
        matches.extend((match.start(), match.end(), kind) for match in pattern.finditer(line))
    matches.sort()
    for index, (_, end, kind) in enumerate(matches):
        next_start = matches[index + 1][0] if index + 1 < len(matches) else len(line)
        yield kind, line[end:next_start]


def _row_prices(line):
    # Strip hashtags/pairs and label ordinal such as TP1, then extract prices.
    stripped = PAIR.sub(" ", line)
    stripped = re.sub(
        r"(?i)\b(?:TP|TARGET)\s*[1-9](?=\s*[:=-])|(?:هدف|تارگت)\s+[1-9](?=\s*[:=-])",
        " ",
        stripped,
    )
    stripped = re.sub(r"(?i)\b(?:LEV(?:ERAGE)?|اهرم)\s*[:=]?\s*\d+(?:\.\d+)?\s*X?", " ", stripped)
    return [v for match in ROW_NUMBERS.finditer(stripped) if (v := _decimal(match.group(1)))]


def extract(raw: str) -> dict:
    cleaned = normalize(raw)
    pairs = []
    for base, quote in PAIR.findall(cleaned):
        pair = f"{base.upper()}/{quote.upper()}"
        if pair not in pairs:
            pairs.append(pair)
    for base, quote in COMPACT_PAIR.findall(PAIR.sub(" ", cleaned)):
        pair = f"{base.upper()}/{quote.upper()}"
        if pair not in pairs:
            pairs.append(pair)
    long = bool(SIDE_LONG.search(cleaned))
    short = bool(SIDE_SHORT.search(cleaned))
    side = "long" if long and not short else "short" if short and not long else None
    entry_values, stops, targets = [], [], []
    leverage = None
    mode = ""
    for line in cleaned.splitlines():
        upper = line.upper()
        if not upper or upper.startswith(("HTTP://", "HTTPS://", "T.ME/")):
            continue
        found_lev = LEVERAGE.search(line)
        if found_lev:
            leverage = _decimal(found_lev.group(1))
        segments = list(_labeled_segments(line))
        if segments:
            for kind, segment in segments:
                values = _row_prices(segment)
                if kind == "entry":
                    entry_values.extend(values)
                elif kind == "sl":
                    stops.extend(values)
                else:
                    targets.extend(values)
            mode = segments[-1][0]
        elif mode == "tp" and re.match(r"^\s*(?:\d+[.)-]|[-•])\s+", line):
            targets.extend(_row_prices(line))
        elif mode == "entry" and re.match(r"^\s*(?:-|TO\b)", line, re.I):
            entry_values.extend(_row_prices(line))
        else:
            mode = ""
    # A labeled range such as 63000 - 65000 is retained as a range, not guessed.
    entry_range = entry_values[:2] if len(entry_values) >= 2 else None
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
        "stop_loss": sl,
        "all_targets": targets,
        "execution_targets": targets[:3],
        "extra_targets": targets[3:],
        "leverage": leverage,
        "futures_mentioned": bool(FUTURES.search(cleaned)),
        "source_hint": "smart_paste",
    }
