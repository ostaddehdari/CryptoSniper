from types import SimpleNamespace
from unittest.mock import patch

from apps.signals.telegram_ingestion import ingest_telegram_message


def test_archive_ingestion_contract_disables_automation_and_live_cursor():
    channel = SimpleNamespace(pk=7, peer_id=-1001, live_message_id=900)
    signal = SimpleNamespace(raw_signal=SimpleNamespace(pk=4), pk=3)
    event = SimpleNamespace(revision=1, save=lambda **kwargs: None)
    with (
        patch("apps.signals.telegram_ingestion.TelegramChannel.objects") as channels,
        patch("apps.signals.telegram_ingestion.receive_signal", return_value=(signal, True, False)),
        patch(
            "apps.signals.telegram_ingestion.TelegramMessage.objects.get_or_create",
            return_value=(event, True),
        ),
        patch("apps.signals.telegram_ingestion._suggestion", return_value={"pair": "BTC/USDT"}),
        patch("apps.signals.telegram_ingestion._store_suggestion", return_value=signal),
        patch("apps.signals.telegram_ingestion._try_full_auto_paper") as auto,
    ):
        channels.select_related.return_value.get.return_value = channel
        channel.owner = object()
        channel.source = object()
        result = ingest_telegram_message(
            7,
            10,
            "BTC/USDT ENTRY 10 TARGET 11 STOP LOSS 9 LONG",
            ingestion_kind="archive",
            advance_live_cursor=False,
            allow_automation=False,
        )
    assert result["created"] is True
    channels.filter.return_value.update.assert_not_called()
    auto.assert_not_called()
