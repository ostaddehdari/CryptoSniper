from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from apps.signals.models import SignalOutcome, SignalSource, TelegramAccount, TelegramChannel
from apps.signals.outcomes import evaluate_path
from django.urls import reverse


def candle(at, low, high):
    return SimpleNamespace(
        open_time=at,
        close_time=at + timedelta(hours=1),
        low_price=low,
        high_price=high,
    )


def test_historical_outcome_requires_entry_before_target():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    result = evaluate_path(
        side="long",
        entry="100",
        stop="90",
        targets=["110"],
        candles=[candle(start, "105", "120"), candle(start + timedelta(hours=1), "99", "101")],
    )
    assert result["status"] == SignalOutcome.Status.OPEN
    assert result["targets_hit"] == 0


def test_historical_outcome_marks_same_candle_tp_sl_ambiguous():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    result = evaluate_path(
        side="long",
        entry="100",
        stop="90",
        targets=["110"],
        candles=[candle(start, "99", "101"), candle(start + timedelta(hours=1), "89", "111")],
    )
    assert result["status"] == SignalOutcome.Status.AMBIGUOUS
    assert result["evidence"]["ambiguous_same_candle"] is True


def test_historical_short_path_hits_ordered_targets():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    result = evaluate_path(
        side="short",
        entry="100",
        stop="110",
        targets=["95", "90"],
        candles=[
            candle(start, "99", "101"),
            candle(start + timedelta(hours=1), "94", "99"),
            candle(start + timedelta(hours=2), "89", "96"),
        ],
    )
    assert result["status"] == SignalOutcome.Status.TARGET
    assert result["targets_hit"] == 2


@pytest.mark.django_db
def test_channel_analytics_is_owner_scoped(client, django_user_model):
    owner = django_user_model.objects.create_user(username="channel-owner")
    stranger = django_user_model.objects.create_user(username="channel-stranger")
    account = TelegramAccount.objects.create(owner=owner)
    source = SignalSource.objects.create(
        owner=owner,
        method=SignalSource.Method.TELEGRAM,
        name="Telegram · Test",
    )
    channel = TelegramChannel.objects.create(
        owner=owner,
        account=account,
        source=source,
        peer_id=-100123,
        title="Test",
    )
    client.force_login(owner)
    assert client.get(reverse("telegram-channel-analytics", args=[channel.pk])).status_code == 200
    payload = client.get(reverse("api-telegram-channel-analytics", args=[channel.pk]))
    assert payload.status_code == 200
    assert payload.json()["metrics"]["total_messages"] == 0
    client.force_login(stranger)
    assert client.get(reverse("telegram-channel-analytics", args=[channel.pk])).status_code == 404
    assert (
        client.get(reverse("api-telegram-channel-analytics", args=[channel.pk])).status_code == 404
    )
