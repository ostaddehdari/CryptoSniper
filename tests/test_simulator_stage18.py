"""Stage 18 deterministic simulator, shared engine and failure matrix."""

from decimal import Decimal

import pytest
from apps.exchanges.adapters import (
    AdapterError,
    OrderStatus,
    SimulationScenario,
    SimulatorAdapter,
)


def test_seeded_price_path_is_reproducible_and_virtual_time_has_no_sleep():
    scenario = SimulationScenario(seed=1801, volatility_bps=40, virtual_latency_ms=250)
    first, second = SimulatorAdapter(scenario=scenario), SimulatorAdapter(scenario=scenario)
    left, right = [], []
    for _ in range(5):
        left.append(first.fetch_ticker("BTC/USDT").price)
        right.append(second.fetch_ticker("BTC/USDT").price)
        first.advance()
        second.advance()
    assert left == right and len(set(left)) > 1
    assert first.virtual_clock_ms == second.virtual_clock_ms == 1250


def test_partial_fill_market_rules_rate_limit_and_rejection_are_deterministic():
    scenario = SimulationScenario(
        seed=18,
        volatility_bps=0,
        partial_fill_ratio=Decimal("0.5"),
        reject_every=2,
        rate_limit_per_step=1,
    )
    adapter = SimulatorAdapter(scenario=scenario)
    first = adapter.place_order(
        client_order_id="partial-1",
        symbol="BTC/USDT",
        side="buy",
        order_type="market",
        amount="0.002000",
    )
    assert first.status == OrderStatus.PARTIAL
    assert first.filled_amount == Decimal("0.001000")
    with pytest.raises(AdapterError, match="simulated_rejection"):
        adapter.place_order(
            client_order_id="rejected-2",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            amount="0.002000",
        )
    with pytest.raises(AdapterError, match="simulated_rate_limit"):
        adapter.fetch_ticker("BTC/USDT")


@pytest.mark.parametrize("amount", ("0.0000001", "0.0000105"))
def test_simulator_enforces_min_notional_and_lot_step(amount):
    adapter = SimulatorAdapter()
    with pytest.raises(ValueError):
        adapter.place_order(
            client_order_id=f"invalid-{amount}",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            amount=amount,
        )


@pytest.mark.django_db
def test_paper_dispatch_uses_shared_engine_without_real_adapter(monkeypatch, django_user_model):
    import uuid

    from apps.trading.execution import dispatch_paper
    from apps.trading.intent import queue_paper_trade
    from test_trading_stage08 import paper_account, ready_plan

    owner = django_user_model.objects.create_user(username="boundary18")
    account, market = paper_account(owner)
    trade, _ = queue_paper_trade(
        owner, ready_plan(owner, account, market).pk, request_key=uuid.uuid4()
    )

    def external_adapter_forbidden(*args, **kwargs):
        raise AssertionError("Paper execution attempted provider adapter selection")

    monkeypatch.setattr("apps.exchanges.adapters.get_adapter", external_adapter_forbidden)
    assert dispatch_paper(trade.orders.get().outbox.pk)["status"] == "filled"
    trade.refresh_from_db()
    assert trade.mode == "paper" and trade.state == "open"


@pytest.mark.django_db
def test_paper_boundary_rejects_revoked_or_live_account(django_user_model):
    import uuid

    from apps.trading.boundary import require_paper_simulator
    from apps.trading.intent import queue_paper_trade
    from test_trading_stage08 import paper_account, ready_plan

    owner = django_user_model.objects.create_user(username="boundary-reject18")
    account, market = paper_account(owner)
    trade, _ = queue_paper_trade(
        owner, ready_plan(owner, account, market).pk, request_key=uuid.uuid4()
    )
    order = trade.orders.select_related("trade", "account__exchange").get()
    account.credentials_encrypted = ""
    account.save(update_fields=("credentials_encrypted", "updated_at"))
    order.account = account
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        require_paper_simulator(order)


def _margin_plan(owner, account, *, side="short"):
    import uuid

    from apps.exchanges.models import ExchangeMarket
    from apps.tradeplans.forms import ManualTradeForm
    from apps.tradeplans.service import approve_plan, create_draft

    market = ExchangeMarket.objects.get(
        exchange=account.exchange, symbol="BTC/USDT", market_type="margin"
    )
    short = side == "short"
    form = ManualTradeForm(
        owner,
        {
            "account": str(account.pk),
            "market": str(market.pk),
            "source": "manual",
            "side": side,
            "entry_price": "65000",
            "tp1": "60000" if short else "70000",
            "tp2": "",
            "tp3": "",
            "stop_loss": "70000" if short else "60000",
            "capital": "100",
            "leverage": "2",
            "trailing_distance": "1",
            "client_token": str(uuid.uuid4()),
        },
    )
    assert form.is_valid(), form.errors
    plan, _ = create_draft(owner, form.cleaned_data)
    return approve_plan(owner, plan.pk, 1)


@pytest.mark.django_db
def test_margin_short_borrow_interest_tp_repay_and_no_dust(django_user_model):
    import uuid

    from apps.trading.execution import dispatch_paper
    from apps.trading.exits_engine import process_paper_price
    from apps.trading.intent import queue_paper_trade
    from apps.trading.margin import accrue_margin_interest
    from apps.trading.models import PaperMarginLoan, Position, TradeFinanceEvent
    from django.utils import timezone
    from test_trading_stage08 import paper_account

    owner = django_user_model.objects.create_user(username="margin-short18")
    account, _ = paper_account(owner)
    trade, _ = queue_paper_trade(owner, _margin_plan(owner, account).pk, request_key=uuid.uuid4())
    assert trade.side == "sell" and trade.margin_loan.asset.symbol == "BTC"
    assert dispatch_paper(trade.orders.get().outbox.pk)["status"] == "filled"
    assert accrue_margin_interest(trade.pk, hours=2) > 0
    result = process_paper_price(
        trade.pk,
        price="60000",
        observed_at=timezone.now(),
        event_key="margin-short-tp",
    )
    assert result["status"] == "closed"
    assert Position.objects.get(trade=trade).quantity == 0
    loan = PaperMarginLoan.objects.get(trade=trade)
    assert loan.state == "repaid" and loan.repaid_amount > loan.principal
    assert set(TradeFinanceEvent.objects.filter(trade=trade).values_list("kind", flat=True)) == {
        "borrow_interest",
        "repayment",
    }


@pytest.mark.django_db
def test_two_margin_trades_have_isolated_loans_and_positions(django_user_model):
    import uuid

    from apps.trading.execution import dispatch_paper
    from apps.trading.intent import queue_paper_trade
    from apps.trading.models import PaperMarginLoan, Position
    from test_trading_stage08 import paper_account

    owner = django_user_model.objects.create_user(username="margin-concurrent18")
    account, _ = paper_account(owner)
    trades = []
    for side in ("long", "short"):
        trade, _ = queue_paper_trade(
            owner, _margin_plan(owner, account, side=side).pk, request_key=uuid.uuid4()
        )
        assert dispatch_paper(trade.orders.get().outbox.pk)["status"] == "filled"
        trades.append(trade)
    assert PaperMarginLoan.objects.filter(trade__in=trades, state="active").count() == 2
    assert Position.objects.filter(trade__in=trades, quantity__gt=0).count() == 2


@pytest.mark.django_db
def test_timeout_after_submit_restart_and_duplicate_recovery_never_double_fills(
    django_user_model,
):
    import uuid

    from apps.operations.failures import inject_paper_failure
    from apps.operations.models import PaperProviderOrder
    from apps.operations.recovery import recover_outbox
    from apps.trading.execution import dispatch_paper
    from apps.trading.intent import queue_paper_trade
    from apps.trading.models import OrderFill
    from test_trading_stage08 import paper_account, ready_plan

    owner = django_user_model.objects.create_user(username="fault-after18")
    account, market = paper_account(owner)
    trade, _ = queue_paper_trade(
        owner, ready_plan(owner, account, market).pk, request_key=uuid.uuid4()
    )
    box = trade.orders.get().outbox
    with inject_paper_failure("after_submit"):
        assert dispatch_paper(box.pk)["status"] == "uncertain"
    assert PaperProviderOrder.objects.filter(account=account).count() == 1
    assert not OrderFill.objects.exists()
    assert recover_outbox(box.pk) == "recovered"
    assert recover_outbox(box.pk) in {"recovered", "unchanged"}
    assert dispatch_paper(box.pk)["status"] == "already_claimed"
    assert OrderFill.objects.count() == 1


@pytest.mark.django_db
def test_timeout_before_submit_stays_unknown_until_authoritative_absence(django_user_model):
    import uuid

    from apps.operations.failures import inject_paper_failure
    from apps.operations.models import PaperProviderOrder
    from apps.operations.recovery import recover_outbox
    from apps.trading.execution import dispatch_paper
    from apps.trading.intent import queue_paper_trade
    from apps.trading.models import Trade
    from django.utils import timezone
    from test_trading_stage08 import paper_account, ready_plan

    owner = django_user_model.objects.create_user(username="fault-before18")
    account, market = paper_account(owner)
    trade, _ = queue_paper_trade(
        owner, ready_plan(owner, account, market).pk, request_key=uuid.uuid4()
    )
    box = trade.orders.get().outbox
    with inject_paper_failure("before_submit"):
        assert dispatch_paper(box.pk)["status"] == "uncertain"
    trade.refresh_from_db()
    assert trade.state == Trade.State.UNCERTAIN
    assert not PaperProviderOrder.objects.exists()
    box.refresh_from_db()
    box.next_attempt_at = timezone.now()
    box.save(update_fields=("next_attempt_at",))
    assert recover_outbox(box.pk) == "retry_pending"
    trade.refresh_from_db()
    assert trade.state == Trade.State.QUEUED


@pytest.mark.django_db
def test_cancel_fill_race_cannot_reopen_cancelled_trade(django_user_model):
    import uuid

    from apps.trading.execution import cancel_unsubmitted, record_fill
    from apps.trading.intent import queue_paper_trade
    from apps.trading.models import Position
    from django.core.exceptions import ValidationError
    from test_trading_stage08 import paper_account, ready_plan

    owner = django_user_model.objects.create_user(username="cancel-race18")
    account, market = paper_account(owner)
    trade, _ = queue_paper_trade(
        owner, ready_plan(owner, account, market).pk, request_key=uuid.uuid4()
    )
    order = trade.orders.get()
    cancel_unsubmitted(owner, trade.pk)
    with pytest.raises(ValidationError):
        record_fill(
            order.pk,
            exchange_fill_id="late-after-cancel",
            quantity=order.quantity,
            price=order.price,
        )
    assert not Position.objects.filter(trade=trade).exists()


@pytest.mark.django_db
def test_readiness_api_reports_provider_limits_without_claiming_live(client, django_user_model):
    from django.urls import reverse

    user = django_user_model.objects.create_user(username="readiness18")
    client.force_login(user)
    payload = client.get(reverse("api-engine-readiness")).json()
    assert payload["release_mode"] == "paper"
    assert payload["real_order_writes"] is False
    assert payload["adapters"]["binance_live_write"] == "disabled_not_verified"
    assert payload["inputs"]["telegram"] == "deferred_to_s21"


@pytest.mark.django_db
def test_manual_trade_reaches_alert_shutdown_and_financial_report(django_user_model):
    import uuid

    from apps.alerts.models import PriceAlert
    from apps.reports.stats import report_statistics
    from apps.trading.execution import dispatch_paper
    from apps.trading.exits_engine import process_paper_price
    from apps.trading.intent import queue_paper_trade
    from django.utils import timezone
    from test_trading_stage08 import paper_account, ready_plan

    owner = django_user_model.objects.create_user(username="e2e-manual18")
    account, market = paper_account(owner)
    trade, _ = queue_paper_trade(
        owner, ready_plan(owner, account, market).pk, request_key=uuid.uuid4()
    )
    assert dispatch_paper(trade.orders.get().outbox.pk)["status"] == "filled"
    alert = PriceAlert.objects.create(
        owner=owner,
        market=market,
        trade=trade,
        title="E2E",
        kind="price",
        direction="above",
        threshold="70000",
        reference_price="65000",
        reference_at=timezone.now(),
        reference_source="paper",
    )
    result = process_paper_price(
        trade.pk, price="70000", observed_at=timezone.now(), event_key="manual-e2e-close"
    )
    assert result["status"] == "closed"
    alert.refresh_from_db()
    assert not alert.enabled and alert.status == "trade_closed"
    report = report_statistics(owner)
    assert report["buckets"][0]["closed_trades"] == 1


@pytest.mark.django_db
def test_smart_paste_origin_reaches_shared_paper_executor(django_user_model):
    import uuid

    from apps.signals.parsing import parse_for_review
    from apps.signals.services import receive_signal, transition, update_parsed
    from apps.signals.sources import get_default_source
    from apps.tradeplans.forms import ManualTradeForm
    from apps.tradeplans.service import approve_plan, create_draft
    from apps.trading.execution import dispatch_paper
    from apps.trading.intent import queue_paper_trade
    from test_trading_stage08 import paper_account

    owner = django_user_model.objects.create_user(username="e2e-smart18")
    account, market = paper_account(owner)
    source = get_default_source(owner, "smart_paste")
    raw, _, _ = receive_signal(
        owner, source, text="BTC/USDT LONG\nEntry: 65000\nTP1: 70000\nSL: 60000"
    )
    parsed = parse_for_review(owner, raw.pk)
    reviewed = update_parsed(
        owner,
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
        reason="تأیید E2E Stage18",
    )
    signal = transition(owner, raw.pk, expected_revision=reviewed.revision, action="approve")
    form = ManualTradeForm(
        owner,
        {
            "account": account.pk,
            "market": market.pk,
            "source": "smart_paste",
            "origin_signal": signal.pk,
            "side": "long",
            "entry_price": "65000",
            "stop_loss": "60000",
            "tp1": "70000",
            "capital": "50",
            "leverage": "1",
            "trailing_distance": "1",
            "client_token": str(uuid.uuid4()),
        },
    )
    assert form.is_valid(), form.errors
    plan, _ = create_draft(owner, form.cleaned_data)
    approve_plan(owner, plan.pk, plan.revision)
    trade, _ = queue_paper_trade(owner, plan.pk, request_key=uuid.uuid4())
    assert dispatch_paper(trade.orders.get().outbox.pk)["status"] == "filled"
    assert trade.signal_id == signal.pk and trade.plan.source == "smart_paste"
