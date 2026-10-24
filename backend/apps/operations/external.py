"""Read-only snapshots from connected exchanges.

External orders/trades are observed and displayed, never adopted into managed execution.
No write endpoint is called from this module.
"""

import hashlib
import json
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.audit import record_audit
from apps.exchanges.adapters import AdapterError, UnsupportedOperationError, get_adapter
from apps.exchanges.models import Asset, BalanceSnapshot, LiveSpotOrder
from apps.exchanges.security import get_account_credentials

from .models import AccountControl, ExternalObservation


def _safe_scalars(payload, limit=40):
    if not isinstance(payload, dict):
        return {}
    result = {}
    for key, value in payload.items():
        if len(result) >= limit:
            break
        if isinstance(value, (str, int, float, bool, type(None))):
            result[str(key)[:80]] = value
    return result


def _order_payload(order):
    return {
        "symbol": order.symbol,
        "orderId": order.order_id,
        "clientOrderId": order.client_order_id,
        "status": str(order.status),
        "origQty": str(order.amount),
        "executedQty": str(order.filled_amount),
        "price": str(order.price) if order.price is not None else None,
        "averagePrice": str(order.average_price) if order.average_price is not None else None,
        "side": order.side,
        "type": order.order_type,
        "time": order.created_at.isoformat() if order.created_at else None,
        "managed": False,
    }


def _history_id(row, position):
    for key in ("id", "tradeId", "trade_id", "orderId", "order_id", "txId", "transaction_id"):
        value = row.get(key) if isinstance(row, dict) else None
        if value not in (None, ""):
            symbol = row.get("symbol", "") if isinstance(row, dict) else ""
            return f"{symbol}:{value}"[:120]
    raw = json.dumps(_safe_scalars(row), ensure_ascii=False, sort_keys=True, default=str)
    return f"row:{position}:{hashlib.sha256(raw.encode()).hexdigest()[:24]}"


def observe_account(account):
    if account.status not in {"connected", "restricted"} or not account.permissions.get("can_read"):
        return "provider_read_unavailable"
    if account.environment != "live":
        return "non_live_account_skipped"

    adapter = get_adapter(
        account.exchange.adapter_code,
        credentials=get_account_credentials(account),
        environment=account.environment,
    )
    permission = adapter.validate_credentials()
    if not permission.can_read or permission.can_withdraw is not False:
        raise ValidationError("مجوز امن خواندن تأیید نشد.")

    balances = adapter.fetch_balance()
    warnings = []
    if account.exchange.adapter_code == "bitunix":
        symbols = []
        for balance in balances:
            asset = str(balance.asset).upper()
            if asset and asset not in {"USDT", "USDC"} and balance.total > 0:
                symbols.append(f"{asset}/USDT")
        for symbol in LiveSpotOrder.objects.filter(
            account=account,
            state__in=("pending", "submitting", "open", "partial", "uncertain"),
        ).values_list("market__symbol", flat=True)[:40]:
            if symbol and symbol not in symbols:
                symbols.append(symbol)
        for payload in ExternalObservation.objects.filter(
            account=account, kind__in=("order", "fill")
        ).order_by("-observed_at").values_list("payload", flat=True)[:60]:
            if not isinstance(payload, dict):
                continue
            raw_symbol = str(payload.get("symbol") or "").upper().replace("_", "/")
            if "/" not in raw_symbol and raw_symbol.endswith("USDT"):
                raw_symbol = raw_symbol[:-4] + "/USDT"
            if raw_symbol and raw_symbol not in symbols:
                symbols.append(raw_symbol)
        if "BTC/USDT" not in symbols:
            symbols.append("BTC/USDT")
        orders, history = [], []
        for symbol in symbols[:12]:
            try:
                orders.extend(adapter.fetch_open_orders(symbol=symbol))
            except UnsupportedOperationError:
                warnings.append(f"open_orders_unsupported:{symbol}")
            except AdapterError as error:
                warnings.append(f"open_orders_failed:{symbol}:{type(error).__name__}")
            try:
                history.extend(adapter.fetch_trade_history(symbol=symbol))
            except UnsupportedOperationError:
                warnings.append(f"history_unsupported:{symbol}")
            except AdapterError as error:
                warnings.append(f"history_failed:{symbol}:{type(error).__name__}")
    else:
        try:
            orders = adapter.fetch_open_orders()
        except UnsupportedOperationError:
            orders = []
        try:
            history = adapter.fetch_trade_history()
        except UnsupportedOperationError:
            history = []
        except AdapterError:
            history = []

    if not isinstance(history, list):
        history = []
    history = history[:100]
    orders = list(orders)[:250]
    now = timezone.now()

    with transaction.atomic():
        for balance in balances:
            if (
                not balance.free.is_finite()
                or not balance.locked.is_finite()
                or balance.free < Decimal(0)
                or balance.locked < Decimal(0)
            ):
                raise ValidationError("موجودی نامعتبر است.")
            asset, _ = Asset.objects.get_or_create(symbol=balance.asset.upper())
            BalanceSnapshot.objects.create(
                exchange_account=account,
                asset=asset,
                free_balance=balance.free,
                locked_balance=balance.locked,
                total_balance=balance.total,
                captured_at=now,
            )
            ExternalObservation.objects.update_or_create(
                account=account,
                kind="asset",
                external_id=balance.asset.upper()[:120],
                defaults={
                    "payload": {
                        "asset": balance.asset.upper(),
                        "free": str(balance.free),
                        "locked": str(balance.locked),
                        "managed": False,
                    }
                },
            )

        for order in orders:
            payload = _order_payload(order)
            external_id = f"{order.symbol}:{order.order_id}"[:120]
            observation, created = ExternalObservation.objects.update_or_create(
                account=account,
                kind="order",
                external_id=external_id,
                defaults={"payload": payload},
            )
            if created:
                record_audit(
                    "operations.external_observed",
                    user=account.owner,
                    metadata={"account_id": account.pk, "observation_id": observation.pk, "kind": "order"},
                )

        for index, row in enumerate(history):
            payload = _safe_scalars(row)
            payload["managed"] = False
            external_id = _history_id(row, index)
            observation, created = ExternalObservation.objects.update_or_create(
                account=account,
                kind="fill",
                external_id=external_id,
                defaults={"payload": payload},
            )
            if created:
                record_audit(
                    "operations.external_observed",
                    user=account.owner,
                    metadata={"account_id": account.pk, "observation_id": observation.pk, "kind": "fill"},
                )

        AccountControl.objects.update_or_create(account=account, defaults={"last_reconciled_at": now})
        if warnings:
            account.last_error_code = "external_observation_partial"
            account.last_error_message = "; ".join(warnings)[:240]
            account.last_error_at = now
            account.save(
                update_fields=(
                    "last_error_code",
                    "last_error_message",
                    "last_error_at",
                    "updated_at",
                )
            )
        elif account.last_error_code in {"external_observation_partial", "external_refresh_failed"}:
            account.last_error_code = ""
            account.last_error_message = ""
            account.last_error_at = None
            account.save(
                update_fields=(
                    "last_error_code",
                    "last_error_message",
                    "last_error_at",
                    "updated_at",
                )
            )

    return {
        "status": "read_only_snapshot",
        "balances": len(balances),
        "open_orders": len(orders),
        "history": len(history),
        "warnings": warnings,
        "observed_at": now.isoformat(),
    }


# Backwards-compatible alias used by older code/tests.
def observe_binance(account):
    return observe_account(account)
