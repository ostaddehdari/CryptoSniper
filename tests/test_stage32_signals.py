from datetime import timedelta

import pytest
from apps.signals.ai import _validated
from apps.signals.backfill import start_backfill
from apps.signals.models import (
    RawSignal,
    Signal,
    SignalOutcome,
    SignalSource,
    SignalTarget,
    TelegramAccount,
    TelegramBackfillJob,
    TelegramChannel,
)
from apps.signals.parsing import assess
from apps.signals.quality import parser_quality_report
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from test_tradeplans_stage05 import setup_paper


def test_stage32_labeled_smart_paste_quality_is_reproducible():
    report = parser_quality_report()
    assert report["corpus_version"] == "stage32-v1"
    assert report["samples"] >= 6
    assert report["accuracy_percent"] == 100
    assert report["meaning"] == "field_extraction_quality_not_profit_probability"


def test_stage32_confidence_and_validation_are_separate():
    result = assess(
        {
            "pair": "BTC/USDT",
            "side": "long",
            "entry": "100",
            "entry_range": None,
            "stop_loss": "90",
            "all_targets": ["110"],
            "execution_targets": ["110"],
            "extra_targets": [],
            "futures_mentioned": True,
        }
    )
    assert result["confidence_band"] == "high"
    assert result["validation"]["blocked"] is True
    assert result["validation"]["complete"] is False


def test_stage32_ambiguous_ohlc_never_claims_profit():
    from apps.signals.outcomes import evaluate_path

    class Candle:
        low_price = "89"
        high_price = "111"
        open_time = timezone.now()
        close_time = timezone.now()

    result = evaluate_path(side="long", entry="100", stop="90", targets=["110"], candles=[Candle()])
    assert result["status"] == SignalOutcome.Status.AMBIGUOUS
    assert result["evidence"]["intrabar_order_known"] is False
    assert result["evidence"]["profit_claimed"] is False


@pytest.mark.django_db
def test_stage32_quality_endpoint_is_private(client, django_user_model):
    assert client.get(reverse("api-smart-paste-quality")).status_code in {302, 401, 403}
    client.force_login(django_user_model.objects.create_user(username="s32-quality"))
    payload = client.get(reverse("api-smart-paste-quality"))
    assert payload.status_code == 200
    assert payload.json()["quality"]["accuracy_percent"] == 100


def _parsed_signal(user, account, market):
    source = SignalSource.objects.create(owner=user, method="manual", name="S32 manual")
    raw = RawSignal.objects.create(
        owner=user,
        source=source,
        original_text="BTC/USDT LONG ENTRY 65000 TP 70000 SL 60000",
        checksum="3" * 64,
    )
    signal = Signal.objects.create(
        owner=user,
        source=source,
        raw_signal=raw,
        exchange_account=account,
        market=market,
        side="long",
        entry_price="65000",
        stop_loss="60000",
        status="parsed",
        technical_confidence=100,
    )
    SignalTarget.objects.create(signal=signal, position=1, price="70000", share_percent=100)
    return signal


@pytest.mark.django_db
def test_stage32_approve_transfer_uses_exact_immutable_snapshot(client, django_user_model):
    user = django_user_model.objects.create_user(username="s32-transfer")
    account, market = setup_paper(user)
    signal = _parsed_signal(user, account, market)
    client.force_login(user)
    response = client.post(
        reverse("api-inbox-approve-transfer", args=[signal.pk]),
        {"revision": signal.revision},
        content_type="application/json",
    )
    assert response.status_code == 200
    seed = response.json()["manual_seed"]
    assert seed["entry"] == "65000.0000000000000000"
    assert seed["targets"] == [
        {"position": 1, "price": "70000.0000000000000000", "share_percent": "100.00"}
    ]
    assert seed["origin_signal_id"] == signal.pk
    signal.refresh_from_db()
    assert signal.status == Signal.Status.APPROVED
    assert seed["entry"] == signal.approved_snapshot["entry"]


@pytest.mark.django_db
def test_stage32_bulk_soft_delete_is_owner_scoped(client, django_user_model):
    owner = django_user_model.objects.create_user(username="s32-bulk")
    stranger = django_user_model.objects.create_user(username="s32-bulk-other")
    own_account, own_market = setup_paper(owner)
    other_account, other_market = setup_paper(stranger)
    own = _parsed_signal(owner, own_account, own_market)
    other = _parsed_signal(stranger, other_account, other_market)
    client.force_login(owner)
    response = client.post(
        reverse("api-inbox-bulk"),
        {"action": "trash", "ids": [own.pk, other.pk]},
        content_type="application/json",
    )
    assert response.status_code == 200 and response.json()["count"] == 1
    own.refresh_from_db()
    other.refresh_from_db()
    assert own.trashed_at is not None
    assert other.trashed_at is None


@pytest.mark.django_db
def test_stage32_backfill_restart_reuses_cursor_and_respects_floodwait(django_user_model):
    user = django_user_model.objects.create_user(username="s32-backfill")
    account = TelegramAccount.objects.create(owner=user)
    source = SignalSource.objects.create(owner=user, method="telegram", name="S32 channel")
    channel = TelegramChannel.objects.create(
        owner=user, account=account, source=source, peer_id=-1003200, title="Stage32"
    )
    job = TelegramBackfillJob.objects.create(
        owner=user,
        channel=channel,
        status=TelegramBackfillJob.Status.PAUSED,
        cursor_message_id=412,
        upper_message_id=900,
    )
    resumed, created = start_backfill(channel)
    assert created is False and resumed.pk == job.pk
    assert resumed.cursor_message_id == 412
    resumed.status = TelegramBackfillJob.Status.PENDING
    resumed.retry_at = timezone.now() + timedelta(minutes=2)
    resumed.save()
    with pytest.raises(ValidationError, match="FloodWait"):
        start_backfill(channel)


def test_stage32_ai_schema_rejects_unknown_and_nonpositive_values():
    with pytest.raises(ValidationError, match="ناشناخته"):
        _validated({"pair": "BTC/USDT", "place_order": True})
    with pytest.raises(ValidationError, match="entry"):
        _validated({"pair": "BTC/USDT", "entry": "-1", "execution_targets": []})
    with pytest.raises(ValidationError, match="targets"):
        _validated({"pair": "BTC/USDT", "entry": "1", "execution_targets": ["Infinity"]})


@pytest.mark.django_db
def test_stage32_channel_policy_is_owner_scoped_and_full_auto_is_paper_only(
    client, django_user_model
):
    owner = django_user_model.objects.create_user(username="s32-policy")
    stranger = django_user_model.objects.create_user(username="s32-policy-other")
    account = TelegramAccount.objects.create(owner=owner)
    source = SignalSource.objects.create(owner=owner, method="telegram", name="S32 policy")
    channel = TelegramChannel.objects.create(
        owner=owner, account=account, source=source, peer_id=-1003201, title="Policy"
    )
    body = {
        "action": "channel_policy",
        "channel_id": channel.pk,
        "parse_mode": "hybrid",
        "automation": "full_auto",
        "min_confidence": 85,
        "paper_capital": "125",
        "template": {"version": "1", "aliases": {}},
    }
    client.force_login(stranger)
    stranger_response = client.post(
        reverse("api-telegram-action"), body, content_type="application/json"
    )
    assert stranger_response.status_code == 404
    client.force_login(owner)
    response = client.post(reverse("api-telegram-action"), body, content_type="application/json")
    assert response.status_code == 200
    channel.refresh_from_db()
    assert channel.automation == TelegramChannel.Automation.FULL_AUTO
    assert channel.get_automation_display() == "تمام‌خودکار Paper"
