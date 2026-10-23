"""Bounded recovery: look up durable provider results before retrying any intent."""

import random
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.audit import record_audit
from apps.exchanges.adapters import AuthenticationError, UnsupportedOperationError
from apps.exchanges.models import UserExchangeAccount
from apps.trading.models import ExecutionOutbox, Order, Trade, TradeEvent

from .models import AccountControl, RecoveryIssue
from .provider import lookup

MAX_ATTEMPTS = 5


def classify_failure(outbox_id, error):
    permanent = isinstance(error, (ValidationError, AuthenticationError, UnsupportedOperationError))
    code = "permanent_validation" if permanent else "transient_unknown"
    box = ExecutionOutbox.objects.get(pk=outbox_id)
    if box.state == "done":
        return
    delay = min(300, 2 ** min(box.attempts, 8)) + random.randint(0, 5)
    ExecutionOutbox.objects.filter(pk=box.pk).update(
        last_error_code=code,
        dead_letter=permanent or box.attempts >= MAX_ATTEMPTS,
        next_attempt_at=timezone.now() + timedelta(seconds=delay),
    )
    if permanent or box.attempts >= MAX_ATTEMPTS:
        raise_issue(box.order.account_id, f"outbox:{box.pk}", "dead_letter", {"outbox_id": box.pk})


@transaction.atomic
def raise_issue(account_id, key, code, detail=None):
    control, _ = AccountControl.objects.get_or_create(account_id=account_id)
    control = AccountControl.objects.select_for_update().get(pk=control.pk)
    issue, created = RecoveryIssue.objects.get_or_create(
        account_id=account_id,
        key=key,
        defaults={"code": code, "detail": detail or {}},
    )
    if issue.resolved:
        issue.resolved = False
        issue.code = code
        issue.detail = detail or {}
        issue.save()
        created = True
    if not control.paused:
        control.paused, control.reason = True, "reconciliation_required"
        control.version += 1
        control.save()
    if created:
        account = UserExchangeAccount.objects.get(pk=account_id)
        record_audit(
            "operations.discrepancy",
            user=account.owner,
            metadata={"account_id": account_id, "code": code, "key": key},
        )
    return issue


def recover_outbox(outbox_id):
    from apps.trading.execution import consume_receipt

    info = ExecutionOutbox.objects.select_related(
        "order__account__exchange", "order__trade__market"
    ).get(pk=outbox_id)
    if (
        info.order.account.environment != "paper"
        or info.order.account.exchange.adapter_code != "simulator"
    ):
        raise_issue(info.order.account_id, f"outbox:{info.pk}", "unsupported_recovery")
        return "unsupported"
    receipt = lookup(info.order)  # Authoritative Paper provider ledger, not engine state.
    if receipt:
        consume_receipt(info.pk, receipt)
        RecoveryIssue.objects.filter(account=info.order.account, key=f"outbox:{info.pk}").update(
            resolved=True
        )
        TradeEvent.objects.create(trade=info.order.trade, event_type="RECOVERED_PROVIDER_RECEIPT")
        return "recovered"
    with transaction.atomic():
        trade = Trade.objects.select_for_update().get(pk=info.order.trade_id)
        order = Order.objects.select_for_update().get(pk=info.order_id)
        box = ExecutionOutbox.objects.select_for_update().get(pk=info.pk)
        if box.state not in {"uncertain", "error"}:
            return "unchanged"
        if box.dead_letter or box.attempts >= MAX_ATTEMPTS:
            return "dead_letter"
        if box.next_attempt_at > timezone.now():
            return "backoff"
        # Only simulator has authoritative absence + durable client-ID idempotency.
        # No live adapter is retried here.
        if order.filled_quantity:
            return "partial_requires_reconciliation"
        box.state = "pending"
        box.fence += 1
        box.save(update_fields=("state", "fence", "updated_at"))
        trade.state, order.state = "queued", "queued"
        trade.save(update_fields=("state", "updated_at"))
        order.save(update_fields=("state", "updated_at"))
        TradeEvent.objects.create(
            trade=trade, event_type="SAFE_PAPER_RETRY", payload={"fence": box.fence}
        )
    return "retry_pending"


@transaction.atomic
def reconcile_trade(trade_id):
    """Rebuild engine aggregates only from immutable engine fill/exit ledgers."""
    from apps.trading.models import CapitalReservation, Position, TradeProtection

    trade = Trade.objects.select_for_update().get(pk=trade_id)
    orders = list(Order.objects.select_for_update().filter(trade=trade))
    entry_qty, entry_cost, fees = Decimal(0), Decimal(0), Decimal(0)
    for order in orders:
        fills = list(order.fills.all())
        total = sum((f.quantity for f in fills), Decimal(0))
        if total > order.quantity:
            return "overfill"
        entry_qty += total
        entry_cost += sum((f.quantity * f.price for f in fills), Decimal(0))
        fees += sum((f.fee for f in fills), Decimal(0))
        if total and order.filled_quantity != total:
            order.filled_quantity = total
            order.state = "filled" if total == order.quantity else "partial"
            order.save(update_fields=("filled_quantity", "state", "updated_at"))
    exits = list(trade.exit_fills.all())
    remaining = entry_qty - sum((f.quantity for f in exits), Decimal(0))
    fees += sum((f.fee for f in exits), Decimal(0))
    if remaining < 0:
        return "negative_position"
    position = Position.objects.select_for_update().filter(trade=trade).first()
    if not entry_qty:
        return "ok" if not position or not position.quantity else "unbacked_position"
    expected_state = (
        "closed"
        if remaining == 0
        else ("open" if entry_qty == trade.quantity else "partially_filled")
    )
    changed = trade.filled_quantity != entry_qty or trade.state != expected_state
    expected_average = (entry_cost / entry_qty).quantize(Decimal("0.0000000000000001"))
    if not position:
        position = Position.objects.create(trade=trade, account=trade.account)
        changed = True
    if (
        position.quantity != remaining
        or position.total_fees != fees
        or position.average_entry != expected_average
    ):
        position.quantity, position.average_entry, position.total_fees = (
            remaining,
            expected_average,
            fees,
        )
        position.save()
        changed = True
    if changed:
        trade.filled_quantity, trade.state = entry_qty, expected_state
        trade.revision += 1
        trade.save(update_fields=("filled_quantity", "state", "revision", "updated_at"))
        TradeEvent.objects.create(trade=trade, event_type="LEDGER_RECONCILED")
        record_audit(
            "operations.ledger_recovered", user=trade.owner, metadata={"trade_id": trade.pk}
        )
    if not remaining:
        CapitalReservation.objects.filter(trade=trade).update(active=False)
        TradeProtection.objects.filter(trade=trade).update(coverage="closed")
    return "repaired" if changed else "ok"


def reconcile_account(account_id):
    from apps.trading.models import CapitalReservation

    account = UserExchangeAccount.objects.select_related("exchange").get(pk=account_id)
    if account.environment != "paper" or account.exchange.adapter_code != "simulator":
        from .external import observe_external_account

        return observe_external_account(account)
    # Known immutable receipt with missing engine fill is consumed, never submitted again.
    for box_id in (
        ExecutionOutbox.objects.filter(order__account=account)
        .exclude(state="done")
        .values_list("pk", flat=True)[:100]
    ):
        recover_outbox(box_id)
    issues = []
    for trade_id in Trade.objects.filter(account=account).values_list("pk", flat=True)[:1000]:
        code = reconcile_trade(trade_id)
        key = f"trade:{trade_id}"
        if code not in {"ok", "repaired"}:
            issues.append(raise_issue(account.pk, key, code))
        else:
            RecoveryIssue.objects.filter(account=account, key=key).update(resolved=True)
    for asset_id in (
        CapitalReservation.objects.filter(account=account, active=True)
        .values_list("quote_asset_id", flat=True)
        .distinct()
    ):
        reserved = (
            CapitalReservation.objects.filter(
                account=account, quote_asset_id=asset_id, active=True
            ).aggregate(n=Sum("amount"))["n"]
            or 0
        )
        balance = (
            account.balance_snapshots.filter(asset_id=asset_id).order_by("-captured_at").first()
        )
        key = f"balance:{asset_id}"
        if not balance or balance.free_balance < reserved:
            issues.append(raise_issue(account.pk, key, "balance_discrepancy"))
        else:
            RecoveryIssue.objects.filter(account=account, key=key).update(resolved=True)
    AccountControl.objects.update_or_create(
        account=account, defaults={"last_reconciled_at": timezone.now()}
    )
    return "issues" if issues else "ok"
