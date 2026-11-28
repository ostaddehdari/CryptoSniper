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
    assert result["parser_version"] == "rules-v2"
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


@pytest.mark.parametrize(
    "text,blocked",
    [
        ("BTC/USDT #ETHUSDT LONG\nEntry: 65000\nTP1: 70000\nSL: 60000", "pair"),
        ("#BTCUSD #BTCUSDT LONG\nEntry: 65000\nTP1: 70000\nSL: 60000", "pair"),
        ("BTC/USDT LONG SELL\nEntry: 65000\nTP1: 70000\nSL: 60000", "side"),
        ("BTC/USDT LONG\nEntry: 65000\nTP1: 70000", "stop_loss"),
        ("BTC/USDT LONG\nEntry: 65000\nTP1: 70000\nSL: 60000\nSL: 59000", "stop_loss"),
        ("BTC/USDT LONG\nEntry: 1,25\nTP1: 1,30\nSL: 1,10", "entry"),
    ],
)
def test_ambiguous_extraction_stays_review_only(text, blocked):
    parsed = assess(extract(text))
    assert parsed[blocked] is None
    assert parsed["review_required"] is True
    assert parsed["warnings"]
    assert parsed["normalized"] == normalize(text)


def test_url_noise_and_extended_targets_preserve_evidence():
    text = (
        "BTC/USDT LONG\nhttps://example.org/ETH/USDT/SELL\n"
        "Entry: 65,000\nTargets:\n1) 70,000\n2) 71,000\n"
        "TP10: 72,000\nTP11: 73,000\nSL: 60,000"
    )
    parsed = assess(extract(text))
    assert parsed["pair"] == "BTC/USDT"
    assert parsed["side"] == "long"
    assert parsed["entry"] == "65000"
    assert parsed["all_targets"] == ["70000", "71000", "72000", "73000"]
    assert parsed["extra_targets"] == ["73000"]
    assert parsed["review_required"] is True


def test_three_entry_candidates_are_not_misrepresented_as_range():
    parsed = assess(extract("BTC/USDT LONG\nEntry: 60 61 62\nTP1: 70\nSL: 50"))
    assert parsed["entry"] is None and parsed["entry_range"] is None
    assert parsed["entry_candidates"] == ["60", "61", "62"]
    assert any("بیش از دو" in warning for warning in parsed["warnings"])


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


@pytest.mark.django_db
def test_existing_review_reparses_after_parser_upgrade_without_trade(django_user_model):
    user = django_user_model.objects.create_user(username="parse-upgrade")
    source = get_default_source(user, "smart_paste")
    signal, _, _ = receive_signal(
        user, source, text="BTC/USDT #ETHUSDT LONG\nEntry: 65000\nTP1: 70000"
    )
    signal = parse_for_review(user, signal.pk)
    revision = signal.revision
    signal.parser_version = "rules-v1"
    signal.save(update_fields=("parser_version",))
    refreshed = parse_for_review(user, signal.pk)
    assert refreshed.revision == revision + 1
    assert refreshed.parser_version == "rules-v2"
    assert refreshed.parsed_payload["pair"] is None
    assert refreshed.parsed_payload["stop_loss"] is None
    assert refreshed.entry_price is None
    assert refreshed.status == "needs_review"
    assert refreshed.raw_signal.original_text == "BTC/USDT #ETHUSDT LONG\nEntry: 65000\nTP1: 70000"


@pytest.mark.django_db
def test_smart_paste_review_to_approved_plan(django_user_model):
    import uuid
    from decimal import Decimal

    from apps.exchanges.models import Exchange, ExchangeMarket, UserExchangeAccount
    from apps.exchanges.security import set_account_credentials
    from apps.exchanges.services import sync_exchange_account
    from apps.signals.services import transition, update_parsed
    from apps.tradeplans.forms import ManualTradeForm
    from apps.tradeplans.service import approve_plan, create_draft

    user = django_user_model.objects.create_user(username="bridge78")
    exchange = Exchange.objects.get(code="simulator")
    account = UserExchangeAccount(
        owner=user, exchange=exchange, label="bridge", environment="paper"
    )
    set_account_credentials(account, {})
    account.save()
    sync_exchange_account(account)
    market = ExchangeMarket.objects.get(exchange=exchange, symbol="BTC/USDT", market_type="spot")
    source = get_default_source(user, "smart_paste")
    raw, _, _ = receive_signal(
        user, source, text="BTC/USDT LONG\nEntry: 65000\nTP1: 70000\nSL: 60000"
    )
    parsed = parse_for_review(user, raw.pk)
    reviewed = update_parsed(
        user,
        raw.pk,
        expected_revision=parsed.revision,
        data={
            "account_id": account.pk,
            "market_id": market.pk,
            "side": "long",
            "entry_price": Decimal("65000"),
            "stop_loss": Decimal("60000"),
            "targets": [{"price": Decimal("70000")}],
        },
        reason="تأیید با بررسی کامل",
    )
    signal = transition(user, raw.pk, expected_revision=reviewed.revision, action="approve")
    assert signal.status == "approved"
    form = ManualTradeForm(
        user,
        {
            "account": account.pk,
            "market": market.pk,
            "source": "manual",
            "origin_signal": signal.pk,
            "side": "long",
            "entry_price": "65000",
            "stop_loss": "60000",
            "tp1": "70000",
            "tp2": "",
            "tp3": "",
            "capital": "50",
            "leverage": "1",
            "trailing_distance": "1",
            "trailing_sl": "on",
            "percentage_trailing": "on",
            "client_token": str(uuid.uuid4()),
        },
    )
    assert form.is_valid(), form.errors
    plan, created = create_draft(user, form.cleaned_data)
    assert created and plan.origin_signal_id == signal.pk
    approved = approve_plan(user, plan.pk, plan.revision)
    assert approved.status == "ready"
    assert approved.approved_snapshot["origin_signal_id"] == signal.pk
    from apps.trading.intent import queue_paper_trade

    trade, created = queue_paper_trade(user, plan.pk, request_key=uuid.uuid4())
    assert created and trade.signal_id == signal.pk
