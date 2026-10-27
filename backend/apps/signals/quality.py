"""Deterministic, versioned quality evidence for the Smart Paste parser."""

from .parser import PARSER_VERSION, extract
from .parsing import assess

LABELED_CORPUS = (
    {
        "id": "en-long",
        "text": "BTC/USDT LONG\nEntry: 65000\nTP1: 67000\nTP2: 69000\nSL: 62000",
        "expected": {"pair": "BTC/USDT", "side": "long", "review_required": True},
    },
    {
        "id": "fa-long",
        "text": "#ETHUSDT خرید\nورود: 3500\nهدف 1: 3700\nهدف 2: 3900\nحد ضرر: 3300",
        "expected": {"pair": "ETH/USDT", "side": "long", "review_required": True},
    },
    {
        "id": "en-short",
        "text": "SOL/USDT SHORT\nENTRY 180\nTARGET 170\nTARGET 160\nSTOP LOSS 190",
        "expected": {"pair": "SOL/USDT", "side": "short", "review_required": True},
    },
    {
        "id": "ambiguous-range",
        "text": "BTC/USDT LONG\nEntry 64000 - 65000\nTP 68000\nSL 62000",
        "expected": {"pair": "BTC/USDT", "side": "long", "review_required": True},
    },
    {
        "id": "blocked-futures",
        "text": "XRP/USDT FUTURES LONG\nEntry 1\nTP 1.2\nSL .9",
        "expected": {"pair": "XRP/USDT", "side": "long", "review_required": True},
    },
    {
        "id": "noise",
        "text": "Join our VIP channel for the next winning call",
        "expected": {"pair": None, "side": None, "review_required": True},
    },
)


def parser_quality_report():
    """Return reproducible field accuracy without treating confidence as profitability."""

    fields = ("pair", "side", "review_required")
    total = correct = 0
    failures = []
    for sample in LABELED_CORPUS:
        actual = assess(extract(sample["text"]))
        mismatches = {}
        for field in fields:
            if field not in sample["expected"]:
                continue
            total += 1
            expected = sample["expected"][field]
            if actual.get(field) == expected:
                correct += 1
            else:
                mismatches[field] = {"expected": expected, "actual": actual.get(field)}
        if mismatches:
            failures.append({"id": sample["id"], "mismatches": mismatches})
    return {
        "parser_version": PARSER_VERSION,
        "corpus_version": "stage32-v1",
        "samples": len(LABELED_CORPUS),
        "assertions": total,
        "passed": correct,
        "accuracy_percent": round(correct * 100 / total, 2) if total else None,
        "failures": failures,
        "meaning": "field_extraction_quality_not_profit_probability",
    }
