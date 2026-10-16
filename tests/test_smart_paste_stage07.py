import pytest
from apps.signals.normalization import normalize
from apps.signals.parser import extract
from apps.signals.parsing import assess, parse_for_review
from apps.signals.services import receive_signal
from apps.signals.sources import get_default_source

OP = """OP/USDT LONG 📈
Entry: ۱.۲۵
TP1: 1.30
TP2: 1.35
TP3: 1.40
TP4: 1.45
TP5: 1.50
TP6: 1.60
SL: 1.10
Leverage: 3X
Follow our channel 🚀
"""


def test_op_six_targets_are_not_discarded():
    result = extract(OP)
    assert result["pair"] == "OP/USDT"
    assert result["entry"] == "1.25"
    assert result["side"] == "long"
    assert result["execution_targets"] == ["1.30", "1.35", "1.40"]
    assert result["all_targets"] == ["1.30", "1.35", "1.40", "1.45", "1.50", "1.60"]
    assert result["extra_targets"] == ["1.45", "1.50", "1.60"]
    assert result["stop_loss"] == "1.10"
    assert result["parser_version"] == "rules-v1"
    assert assess(result)["trailing_defaults"]["percentage_distance"] == "1"


def test_ambiguous_range_futures_and_conflicting_direction():
    text = "BTC/USDT ETH/USDT LONG SHORT FUTURES\nEntry: 63000-65000\nTP1: 70000"
    p = assess(extract(text))
    assert p["entry"] is None
    assert p["entry_range"] == ["63000", "65000"]
    assert p["side"] is None
    assert p["pair"] is None
    assert p["futures_mentioned"] is True
    assert p["review_required"]
    assert len(p["warnings"]) >= 4


def test_fa_ar_noise_is_idempotent_and_raw_is_not_modified():
    text = "🎯 بیت کوين #BTCUSDT \r\n هدف ۱: ۷۰،۰۰۰  🚀"
    cleaned = normalize(text)
    assert normalize(cleaned) == cleaned
    assert "كوين" not in cleaned
    assert "70000" in cleaned or "70,000" in cleaned
    assert text.startswith("🎯")


@pytest.mark.django_db
def test_smart_paste_review_never_auto_approves(django_user_model):
    user = django_user_model.objects.create_user(username="parse7")
    source = get_default_source(user, "smart_paste")
    signal, created, _ = receive_signal(user, source, text=OP)
    assert created
    parsed = parse_for_review(user, signal.pk)
    assert parsed.status == "needs_review"
    assert parsed.entry_price is None
    assert parsed.parsed_payload["extra_targets"] == ["1.45", "1.50", "1.60"]
    assert parsed.raw_signal.original_text == OP
    same = parse_for_review(user, signal.pk)
    assert same.revision == parsed.revision
