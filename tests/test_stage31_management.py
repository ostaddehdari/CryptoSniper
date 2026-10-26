import os
import subprocess
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from urllib.parse import quote, urlsplit, urlunsplit

import pytest
from apps.accounts.security import STEP_UP_SESSION_KEY
from apps.exchanges.adapters import InvalidProviderResponse
from apps.exchanges.live_orders import execute_live_spot_order
from apps.exchanges.models import BalanceSnapshot, LiveSpotOrder
from apps.exchanges.reconciliation import apply_receipt, reconcile_order
from apps.operations.models import ExternalObservation, LiveExitAttempt, ManagedSpotPosition
from apps.portfolio.live_management import create_entry_position, monitor_position, sync_inventory
from apps.portfolio.management_api import change_position
from django.core.exceptions import ValidationError
from django.db import connection, connections
from django.urls import reverse
from django.utils import timezone
from stage31_contract_provider import ReceiptProvider
from test_stage30_workflow import workspace as workspace  # noqa: F401

D = Decimal


@pytest.fixture
def managed(workspace, settings, monkeypatch):
    settings.LIVE_TRADING_ENABLED = settings.LIVE_EXIT_MANAGEMENT_ENABLED = True
    owner, account, market = workspace
    entry = LiveSpotOrder.objects.create(
        owner=owner,
        account=account,
        market=market,
        client_order_id="s31-entry-" + uuid.uuid4().hex,
        order_type="limit",
        side="buy",
        amount=1,
        price=100,
        filled_amount=1,
        average_price=100,
        state="filled",
        external_order_id="entry-proof",
    )
    snapshot = {
        "entry_price": "100",
        "stop_loss": "95",
        "tp_distribution": [10, 10, 80],
        "targets": [
            {"price": "110", "share_percent": "10"},
            {"price": "120", "share_percent": "10"},
            {"price": "130", "share_percent": "80"},
        ],
        "trailing_sl": True,
        "percentage_trailing": False,
        "trailing_trigger": "tp2",
        "trailing_distance_percent": "2",
    }
    position = create_entry_position(entry, snapshot)
    control = ExternalObservation.objects.create(
        account=account,
        kind="s31-contract",
        external_id="control",
        payload={"price": "100", "free": "10", "writes": 0},
    )
    provider = ReceiptProvider(account.pk)
    monkeypatch.setattr("apps.portfolio.live_management.account_adapter", lambda a: provider)
    monkeypatch.setattr("apps.exchanges.reconciliation.account_adapter", lambda a: provider)
    monkeypatch.setattr("apps.exchanges.live_orders.get_account_credentials", lambda a: {})
    monkeypatch.setattr("apps.exchanges.live_orders.get_adapter", lambda *a, **k: provider)
    monkeypatch.setattr("apps.tradeplans.submission._dispatch", lambda pk: None)
    BalanceSnapshot.objects.create(
        exchange_account=account,
        asset=market.base_asset,
        wallet_scope="spot",
        free_balance=10,
        total_balance=10,
        captured_at=timezone.now(),
    )
    return owner, position, provider, control


def control(row, **changes):
    row.refresh_from_db()
    row.payload.update(changes)
    row.save()


def authorize(client, owner):
    client.force_login(owner)
    s = client.session
    s[STEP_UP_SESSION_KEY] = timezone.now().isoformat()
    s.save()


@pytest.mark.django_db
def test_tp_partial_cancel_then_sl_uses_only_remaining(managed):
    _, p, provider, ctl = managed
    control(ctl, price="110", fill_ratio="0.5")
    result = monitor_position(p.pk)
    attempt = LiveExitAttempt.objects.get(position=p)
    assert result["status"] == "exit_queued" and attempt.order.amount == D("0.100")
    assert execute_live_spot_order(attempt.order_id)["status"] == "partial"
    for _ in range(2):
        monitor_position(p.pk)
    p.refresh_from_db()
    assert p.remaining == D("0.95") and p.effective_stop == 100 and p.break_even_applied
    control(ctl, price="99", fill_ratio="1")
    assert monitor_position(p.pk)["status"] == "cancellation_checked"
    assert monitor_position(p.pk)["status"] == "exit_queued"
    last = p.exits.latest("sequence")
    assert last.reason == "sl" and last.order.amount == D("0.950")
    assert execute_live_spot_order(last.order_id)["status"] == "filled"
    monitor_position(p.pk)
    p.refresh_from_db()
    assert p.state == "closed" and p.remaining == 0
    assert p.exits.count() == 2


@pytest.mark.django_db
def test_trailing_survives_reload_and_never_weakens(managed):
    _, p, _, ctl = managed
    p.snapshot["percentage_trailing"] = True
    p.save()
    control(ctl, price="110")
    monitor_position(p.pk)
    p.refresh_from_db()
    assert p.break_even_applied and p.effective_stop == 100 and not p.trailing_active
    # Trigger TP2: no target sale at/after TP2; remaining is protected by trailing.
    control(ctl, price="125")
    monitor_position(p.pk)
    p.refresh_from_db()
    assert p.trailing_active and p.high_water == 125 and p.effective_stop == D("122.50")
    control(ctl, price="124")
    monitor_position(p.pk)
    reloaded = ManagedSpotPosition.objects.get(pk=p.pk)
    assert reloaded.effective_stop == D("122.50") and reloaded.high_water == 125


@pytest.mark.django_db
@pytest.mark.parametrize("changes", [{"offline": True}, {"age": 60}, {"age": -60}])
def test_unavailable_feed_never_sends_or_moves_stop(managed, changes):
    _, p, _, ctl = managed
    control(ctl, price="90", **changes)
    assert monitor_position(p.pk)["status"] == "waiting_evidence"
    p.refresh_from_db()
    assert p.effective_stop == 95 and p.last_price_at is None and not p.exits.exists()
    control(ctl, offline=False, age=0)
    assert monitor_position(p.pk)["status"] == "exit_queued"


@pytest.mark.django_db
def test_unknown_receipt_and_repeated_worker_never_resubmit(managed, monkeypatch):
    _, p, provider, ctl = managed
    control(ctl, price="90", fill_ratio="0")
    monitor_position(p.pk)
    attempt = p.exits.get()
    original = provider.place_order

    def lost(**intent):
        original(**intent)
        raise TimeoutError("contract response lost after provider commit")

    monkeypatch.setattr(provider, "place_order", lost)
    assert execute_live_spot_order(attempt.order_id)["status"] == "uncertain"
    assert execute_live_spot_order(attempt.order_id)["status"] == "uncertain"
    assert reconcile_order(attempt.order_id) == "open"
    monitor_position(p.pk)
    assert p.exits.count() == 1 and provider.control().payload["writes"] == 1


@pytest.mark.django_db
def test_receipt_regression_rejected_without_mutating_inventory(managed):
    _, p, provider, ctl = managed
    control(ctl, price="90", fill_ratio="0.5")
    monitor_position(p.pk)
    o = p.exits.get().order
    execute_live_spot_order(o.pk)
    proof = ExternalObservation.objects.get(external_id="receipt-" + o.client_order_id)
    proof.payload["filled"] = "0.1"
    proof.save()
    with pytest.raises(InvalidProviderResponse):
        apply_receipt(o.pk, provider.fetch_order(proof.external_id))
    o.refresh_from_db()
    assert o.filled_amount == D("0.5")


@pytest.mark.django_db
def test_partial_entry_must_be_cancelled_before_exit(managed):
    _, p, provider, ctl = managed
    entry = p.entry_order
    entry.state = "partial"
    entry.filled_amount = D("0.5")
    entry.external_order_id = "entry-proof"
    entry.save()
    ExternalObservation.objects.create(
        account=entry.account,
        kind="s31-contract",
        external_id="entry-proof",
        payload={
            "client": entry.client_order_id,
            "symbol": "BTC/USDT",
            "side": "buy",
            "price": "100",
            "amount": "1",
            "filled": "0.5",
            "status": "partial",
        },
    )
    control(ctl, price="90")
    assert monitor_position(p.pk)["status"] == "cancellation_checked"
    assert not p.exits.exists()
    assert monitor_position(p.pk)["status"] == "exit_queued"
    assert p.exits.get().order.amount == D("0.500")


@pytest.mark.django_db
def test_balance_shortfall_does_not_sell_other_inventory(managed):
    _, p, _, ctl = managed
    control(ctl, price="90", free="0.9")
    assert monitor_position(p.pk)["status"] == "review"
    assert not p.exits.exists()


@pytest.mark.django_db
def test_archive_does_not_disable_protection_and_gate_remains_explicit(managed, settings):
    _, p, _, ctl = managed
    p.entry_order.archived_at = timezone.now()
    p.entry_order.save()
    control(ctl, price="90")
    settings.LIVE_EXIT_MANAGEMENT_ENABLED = False
    assert monitor_position(p.pk)["status"] == "safety_gate_closed"
    assert not p.exits.exists()
    settings.LIVE_EXIT_MANAGEMENT_ENABLED = True
    assert monitor_position(p.pk)["status"] == "exit_queued"


@pytest.mark.django_db
def test_versioned_pause_edit_and_stop_cannot_weaken(managed):
    owner, p, _, _ = managed
    p = sync_inventory(p.pk)
    p = change_position(owner, p.pk, {"action": "pause", "version": p.version, "confirmed": True})
    assert p.paused
    with pytest.raises(ValidationError):
        change_position(owner, p.pk, {"action": "resume", "version": 1, "confirmed": True})
    with pytest.raises(ValidationError):
        change_position(
            owner,
            p.pk,
            {
                "action": "update",
                "version": p.version,
                "confirmed": True,
                "stop_loss": "94",
                "tp1": "110",
            },
        )
    p = change_position(
        owner,
        p.pk,
        {
            "action": "update",
            "version": p.version,
            "confirmed": True,
            "stop_loss": "96",
            "tp1": "112",
            "trailing_trigger": "tp1",
        },
    )
    assert p.effective_stop == 96


@pytest.mark.django_db
def test_external_adoption_is_explicit_scoped_and_cannot_overallocate(
    client, managed, django_user_model
):
    owner, p, _, _ = managed
    item = ExternalObservation.objects.create(
        account=p.account,
        kind="fill",
        external_id="outside-1",
        payload={"symbol": "BTC/USDT", "side": "buy", "qty": "1", "price": "100"},
    )
    url = reverse("api-external-management", args=[item.pk])
    data = {
        "entry_price": "100",
        "remaining_amount": "1",
        "stop_loss": "95",
        "tp1": "110",
        "trailing_trigger": "1",
        "trailing_distance_percent": "1",
        "confirmed": True,
    }
    client.force_login(owner)
    assert client.post(url, data, content_type="application/json").status_code == 403
    authorize(client, owner)
    assert (
        client.post(url, {**data, "confirmed": False}, content_type="application/json").status_code
        == 400
    )
    r = client.post(url, data, content_type="application/json")
    assert r.status_code == 201, r.content
    assert client.post(url, data, content_type="application/json").status_code == 400
    other = django_user_model.objects.create_user(username="s31-other")
    client.force_login(other)
    assert client.get(url).status_code == 404


@pytest.mark.django_db
def test_unified_pagination_has_no_old_200_cap(client, workspace):
    owner, account, market = workspace
    LiveSpotOrder.objects.bulk_create(
        [
            LiveSpotOrder(
                owner=owner,
                account=account,
                market=market,
                client_order_id=f"s31-page-{i}",
                side="buy",
                amount=1,
                price=100,
                state="filled",
            )
            for i in range(225)
        ]
    )
    client.force_login(owner)
    seen = set()
    for offset in (0, 100, 200):
        r = client.get(
            reverse("api-stage24-trades"), {"origin": "live", "state": "closed", "offset": offset}
        )
        assert r.status_code == 200, r.content
        assert r.json()["total"] == 225
        keys = {x["key"] for x in r.json()["trades"]}
        assert not seen & keys
        seen |= keys
    assert len(seen) == 225


@pytest.mark.django_db(transaction=True)
def test_parallel_exit_monitors_reserve_once(managed):
    _, p, _, ctl = managed
    control(ctl, price="90")
    barrier = Barrier(2)

    def worker():
        connections.close_all()
        try:
            barrier.wait(timeout=10)
            return monitor_position(p.pk)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: worker(), range(2)))
    assert p.exits.count() == 1


@pytest.mark.django_db(transaction=True)
def test_real_celery_worker_restart_keeps_trailing_and_one_exit(managed):
    _, p, _, ctl = managed
    p.snapshot["percentage_trailing"] = True
    p.snapshot["trailing_trigger"] = "tp1"
    p.save()
    control(ctl, price="125")
    from apps.operations.tasks import monitor_managed_spot

    env = os.environ.copy()
    parsed = urlsplit(env["DATABASE_URL"])
    env["DATABASE_URL"] = urlunsplit(
        parsed._replace(path="/" + quote(connection.settings_dict["NAME"]))
    )
    root = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = str(root / "tests") + os.pathsep + str(root / "backend")
    env["LIVE_TRADING_ENABLED"] = env["LIVE_EXIT_MANAGEMENT_ENABLED"] = "true"
    env["C_FORCE_ROOT"] = "true"
    queue = "s31-" + uuid.uuid4().hex
    env["STAGE31_TEST_QUEUE"] = queue
    from kombu import Exchange, Queue

    monitor_managed_spot.app.amqp.queues.add(
        Queue(queue, exchange=Exchange(queue), routing_key=queue)
    )

    def run_worker():
        log = tempfile.TemporaryFile(mode="w+")
        process = subprocess.Popen(
            [
                str(root / ".venv/bin/python"),
                "-m",
                "celery",
                "-A",
                "config",
                "worker",
                "-P",
                "solo",
                "-Q",
                queue,
                "-n",
                queue + "@%h",
                "-I",
                "stage31_worker_fixture",
                "--loglevel=ERROR",
                "--without-gossip",
                "--without-mingle",
            ],
            cwd=root / "backend",
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            result = monitor_managed_spot.apply_async(
                queue=queue, exchange=queue, routing_key=queue
            )
            assert result.get(timeout=35, disable_sync_subtasks=False)
        except Exception:
            log.flush()
            log.seek(0)
            print("Contract worker diagnostic: " + log.read()[-5000:])
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            log.close()

    run_worker()
    p.refresh_from_db()
    assert p.trailing_active and p.effective_stop == D("122.5") and p.high_water == 125
    control(ctl, price="121")
    run_worker()
    p.refresh_from_db()
    assert p.effective_stop == D("122.5") and p.exits.count() == 1
    assert p.exits.get().order.amount == 1


@pytest.mark.django_db
def test_chart_stale_is_explicit_and_managed_markers_are_receipts(client, managed, monkeypatch):
    owner, p, _, _ = managed
    authorize(client, owner)
    quote = {
        "price": "100",
        "stale": True,
        "observed_at": (timezone.now() - timedelta(seconds=70)).isoformat(),
        "age_seconds": 70,
        "source": "s31-contract",
    }
    monkeypatch.setattr("apps.marketdata.chart.get_quote", lambda m: quote)
    monkeypatch.setattr("apps.marketdata.chart.refresh_quote", lambda m: None)
    r = client.get(reverse("api-market-chart"), {"market": p.market_id, "position": p.pk})
    assert r.status_code == 200, r.content
    data = r.json()
    assert data["feed"]["stale"] and data["candle_source"] == "binance_public_display_reference"
    assert not any(c.get("live") for c in data["candles"])
    assert data["overlay"]["markers_are_receipts"]
    assert not any(m["kind"].startswith("tp") for m in data["overlay"]["markers"])
