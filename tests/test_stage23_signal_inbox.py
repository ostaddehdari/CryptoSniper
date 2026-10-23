import pytest
from apps.signals.models import RawSignal, Signal, SignalSource, SignalTarget
from test_tradeplans_stage05 import setup_paper


def make_signal(user, *, status="new", account=None, market=None):
    source = SignalSource.objects.create(owner=user, method="manual", name="S23 source")
    raw = RawSignal.objects.create(
        owner=user,
        source=source,
        original_text="BTC/USDT LONG 65000 TP 70000 SL 60000",
        checksum="a" * 64,
    )
    signal = Signal.objects.create(
        owner=user,
        source=source,
        raw_signal=raw,
        status=status,
        exchange_account=account,
        market=market,
        side="long" if market else "",
        entry_price="65000" if market else None,
        stop_loss="60000" if market else None,
        technical_confidence=100 if market else 0,
    )
    if market:
        SignalTarget.objects.create(
            signal=signal, position=1, price="70000", share_percent="100"
        )
    return signal


@pytest.mark.django_db
def test_bulk_trash_is_soft_and_restorable(client, django_user_model):
    user = django_user_model.objects.create_user(username="s23-trash")
    signal = make_signal(user)
    client.force_login(user)
    response = client.post("/inbox/bulk/trash/", {"signal_ids": [signal.pk]})
    assert response.status_code == 302
    signal.refresh_from_db()
    assert signal.trashed_at is not None
    assert str(signal.pk) not in client.get("/inbox/").content.decode()
    assert str(signal.pk) in client.get("/inbox/?trash=1").content.decode()
    client.post("/inbox/bulk/restore/", {"signal_ids": [signal.pk]})
    signal.refresh_from_db()
    assert signal.trashed_at is None


@pytest.mark.django_db
def test_approve_and_trade_is_one_atomic_user_flow(client, django_user_model):
    user = django_user_model.objects.create_user(username="s23-approve-trade")
    account, market = setup_paper(user)
    signal = make_signal(user, status="parsed", account=account, market=market)
    client.force_login(user)
    response = client.post(
        f"/inbox/{signal.pk}/approve-trade/", {"revision": signal.revision}
    )
    assert response.status_code == 302
    assert f"/manual/new/?signal={signal.pk}" in response["Location"]
    signal.refresh_from_db()
    assert signal.status == "approved"
