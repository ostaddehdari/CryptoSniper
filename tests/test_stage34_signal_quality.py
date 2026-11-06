from apps.signals.parser import extract
from apps.signals.parsing import assess
from apps.signals.quality import parser_quality_report


def test_stage34_bilingual_corpus_is_reproducible_and_review_only():
    report = parser_quality_report()
    assert report["corpus_version"] == "stage34-v2"
    assert report["samples"] == 20
    assert report["assertions"] == 140
    assert report["passed"] == 140
    assert report["accuracy_percent"] == 100
    assert report["owner_review_enforced"] is True


def test_stage34_single_line_persian_signal_extracts_execution_fields():
    parsed = assess(
        extract("BTCIRT خرید ورود 4500000000 هدف 4700000000 حد ضرر 4300000000")
    )
    assert parsed["pair"] == "BTC/IRT"
    assert parsed["side"] == "long"
    assert parsed["entry"] == "4500000000"
    assert parsed["stop_loss"] == "4300000000"
    assert parsed["execution_targets"] == ["4700000000"]
    assert parsed["completeness_percent"] == 100
    assert parsed["review_required"] is True
    assert parsed["execution_safe"] is False


def test_stage34_ambiguous_signal_never_becomes_execution_safe():
    parsed = assess(extract("BTC/USDT or ETH/USDT BUY or SELL ENTRY 100 TP 110 SL 90"))
    assert parsed["pair"] is None
    assert parsed["side"] is None
    assert parsed["validation"]["complete"] is False
    assert parsed["review_required"] is True
    assert parsed["execution_safe"] is False
