import json

import pytest
from apps.signals.models import RawSignal, Signal, SignalSource
from django.urls import reverse


@pytest.mark.django_db
def test_stage25_reject_deletes_signal_and_raw_input(client, django_user_model):
    owner = django_user_model.objects.create_user(username="stage25-signal")
    source = SignalSource.objects.create(
        owner=owner,
        name="Stage25 manual",
        method=SignalSource.Method.MANUAL,
    )
    raw = RawSignal.objects.create(
        owner=owner,
        source=source,
        original_text="BTCUSDT entry 100 tp 110 sl 95",
        original_payload={},
        checksum="stage25-delete-signal",
        received_version="v1",
    )
    signal = Signal.objects.create(
        owner=owner,
        source=source,
        raw_signal=raw,
        status=Signal.Status.NEW,
    )
    client.force_login(owner)
    response = client.post(
        reverse("api-inbox-action", args=[signal.pk]),
        data=json.dumps(
            {
                "revision": signal.revision,
                "action": "reject",
                "reason": "",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["deleted"] is True
    assert not Signal.objects.filter(pk=signal.pk).exists()
    assert not RawSignal.objects.filter(pk=raw.pk).exists()
