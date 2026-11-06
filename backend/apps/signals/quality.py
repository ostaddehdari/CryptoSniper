"""Deterministic, versioned quality evidence for the Smart Paste parser."""

import json
from pathlib import Path

from .parser import PARSER_VERSION, extract
from .parsing import assess

CORPUS_VERSION = "stage34-v2"
CORPUS_PATH = Path(__file__).with_name("corpus") / f"{CORPUS_VERSION}.json"


def labeled_corpus():
    value = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not value:
        raise ValueError("Signal quality corpus is empty.")
    return value


def parser_quality_report():
    """Score execution fields without treating confidence as profitability."""

    fields = (
        "pair",
        "side",
        "entry",
        "stop_loss",
        "execution_targets",
        "review_required",
        "execution_safe",
    )
    total = correct = 0
    failures = []
    corpus = labeled_corpus()
    field_totals = {field: {"passed": 0, "assertions": 0} for field in fields}
    for sample in corpus:
        actual = assess(extract(sample["text"]))
        mismatches = {}
        for field in fields:
            if field not in sample["expected"]:
                continue
            total += 1
            field_totals[field]["assertions"] += 1
            expected = sample["expected"][field]
            if actual.get(field) == expected:
                correct += 1
                field_totals[field]["passed"] += 1
            else:
                mismatches[field] = {"expected": expected, "actual": actual.get(field)}
        if mismatches:
            failures.append({"id": sample["id"], "mismatches": mismatches})
    return {
        "parser_version": PARSER_VERSION,
        "corpus_version": CORPUS_VERSION,
        "samples": len(corpus),
        "assertions": total,
        "passed": correct,
        "accuracy_percent": round(correct * 100 / total, 2) if total else None,
        "failures": failures,
        "field_metrics": field_totals,
        "owner_review_enforced": all(
            assess(extract(sample["text"]))["review_required"] for sample in corpus
        ),
        "meaning": "field_extraction_quality_not_profit_probability",
    }
