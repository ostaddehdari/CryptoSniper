import pytest
from apps.signals.models import RawSignal, Signal, SignalSource, SignalTarget
from apps.signals.parsing import assess
from apps.signals.quality import parser_quality_report
from django.urls import reverse
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
