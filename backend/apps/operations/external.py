"""Read-only external Spot snapshots for connected accounts.

Observation never infers a position. Management is a separate explicit user-confirmed policy.
"""

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.audit import record_audit
from apps.exchanges.adapters import UnsupportedOperationError, get_adapter
from apps.exchanges.models import Asset, BalanceSnapshot
from apps.exchanges.security import get_account_credentials

from .models import AccountControl, ExternalObservation


def _rows(payload, required):
    if not isinstance(payload, list) or len(payload) > 5000:
        raise ValidationError("پاسخ مشاهدهٔ صرافی معتبر یا محدود نیست.")
    if any(not isinstance(row, dict) or required - row.keys() for row in payload):
        raise ValidationError("پاسخ مشاهدهٔ صرافی ناقص است.")
    return payload


def _observe_binance(account):
    if (
        account.exchange.adapter_code != "binance"
        or account.status not in {"connected", "restricted"}
        or not account.permissions.get("can_read")
    ):
        return "provider_read_unavailable"
    adapter = get_adapter(
        "binance", credentials=get_account_credentials(account), environment=account.environment
    )
    permission = adapter.validate_credentials()
    if not permission.can_read or permission.can_withdraw is not False:
        raise ValidationError("مجوز امن خواندن تأیید نشد.")
    balances = adapter.fetch_balance()
    orders = _rows(
        adapter._request("/api/v3/openOrders", signed=True),
        {"symbol", "orderId", "clientOrderId", "status", "origQty", "executedQty"},
    )
    # History scope is explicit and bounded, not a claim of full account history.
    symbols = list(
        account.exchange.markets.filter(
            market_type="spot", watchlist_items__watchlist__owner=account.owner
        )
        .values_list("symbol", flat=True)
        .distinct()[:4]
    )
    fills = []
    for symbol in symbols:
        rows = _rows(
            adapter._request(
                "/api/v3/myTrades",
                params={"symbol": symbol.replace("/", ""), "limit": 100},
                signed=True,
            ),
            {"symbol", "id", "orderId", "price", "qty", "commission", "commissionAsset"},
        )
        fills.extend(rows)
    allowed_order = {
        "symbol",
        "orderId",
        "clientOrderId",
        "status",
        "origQty",
        "executedQty",
        "price",
        "side",
        "type",
        "time",
        "updateTime",
    }
    allowed_fill = {
        "symbol",
        "id",
        "orderId",
        "price",
        "qty",
        "commission",
        "commissionAsset",
        "time",
        "isBuyer",
    }
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
            asset, _ = Asset.objects.get_or_create(symbol=balance.asset)
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
                external_id=balance.asset,
                defaults={
                    "payload": {
                        "free": str(balance.free),
                        "locked": str(balance.locked),
                        "managed": False,
                    }
                },
            )
        for kind, rows, keys, id_field in [
            ("order", orders, allowed_order, "orderId"),
            ("fill", fills, allowed_fill, "id"),
        ]:
            for row in rows:
                external_id = f"{row['symbol']}:{row[id_field]}"
                if len(external_id) > 120:
                    raise ValidationError("شناسه خارجی بیش از حد طولانی است.")
                observation, created = ExternalObservation.objects.update_or_create(
                    account=account,
                    kind=kind,
                    external_id=external_id,
                    defaults={
                        "payload": {**{k: v for k, v in row.items() if k in keys}, "managed": False}
                    },
                )
                if created:
                    record_audit(
                        "operations.external_observed",
                        user=account.owner,
                        metadata={
                            "account_id": account.pk,
                            "observation_id": observation.pk,
                            "kind": kind,
                        },
                    )
        AccountControl.objects.update_or_create(
            account=account, defaults={"last_reconciled_at": now}
        )
    return "read_only_snapshot"


_SAFE_HISTORY_KEYS = {
    "symbol", "orderId", "id", "tradeId", "clientOrderId", "status", "side", "type",
    "price", "avgPrice", "averagePrice", "amount", "origQty", "quantity", "qty",
    "executedQty", "filledAmount", "matchedAmount", "dealVolume", "time", "ctime",
    "create_time", "transactTime", "updateTime", "isBuyer", "commission",
    "commissionAsset",
}


def _plain(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)[:200]


def _order_payload(order):
    if not is_dataclass(order):
        raise ValidationError("ساختار سفارش خارجی معتبر نیست.")
    row = asdict(order)
    return {key: _plain(value) for key, value in row.items()}


def _history_payload(row):
    if is_dataclass(row):
        return _order_payload(row)
    if not isinstance(row, dict):
        raise ValidationError("ردیف تاریخچه صرافی معتبر نیست.")
    return {key: _plain(value) for key, value in row.items() if key in _SAFE_HISTORY_KEYS}


def _external_id(payload):
    symbol = str(payload.get("symbol", "")).upper()
    identity = next(
        (
            payload.get(key)
            for key in ("tradeId", "id", "orderId", "client_order_id", "clientOrderId")
            if payload.get(key) not in {None, ""}
        ),
        None,
    )
    if identity is None:
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()[:24]
        identity = digest
    value = f"{symbol}:{identity}" if symbol else str(identity)
    if len(value) > 120:
        value = hashlib.sha256(value.encode()).hexdigest()
    return value


def _save_generic(account, kind, payload):
    observation, created = ExternalObservation.objects.update_or_create(
        account=account,
        kind=kind,
        external_id=_external_id(payload),
        defaults={"payload": {**payload, "managed": False}},
    )
    if created:
        record_audit(
            "operations.external_observed",
            user=account.owner,
            metadata={
                "account_id": account.pk,
                "observation_id": observation.pk,
                "kind": kind,
            },
        )
    return observation


def observe_external_account(account):
    """Refresh bounded read-only observations for every supported real Spot adapter."""
    if account.exchange.adapter_code == "binance":
        return _observe_binance(account)
    if (
        account.environment == "paper"
        or account.status not in {"connected", "restricted"}
        or not account.permissions.get("can_read")
    ):
        return "provider_read_unavailable"
    adapter = get_adapter(
        account.exchange.adapter_code,
        credentials=get_account_credentials(account),
        environment=account.environment,
    )
    permission = adapter.validate_credentials()
    if not permission.can_read or permission.can_withdraw is True:
        raise ValidationError("مجوز امن خواندن تأیید نشد.")
    balances = adapter.fetch_balance()
    try:
        orders = list(adapter.fetch_open_orders())[:200]
    except UnsupportedOperationError:
        orders = []
    try:
        history = list(adapter.fetch_trade_history())[:200]
    except UnsupportedOperationError:
        history = []
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
            asset, _ = Asset.objects.get_or_create(symbol=balance.asset)
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
                external_id=balance.asset,
                defaults={
                    "payload": {
                        "free": str(balance.free),
                        "locked": str(balance.locked),
                        "managed": False,
                    }
                },
            )
        for order in orders:
            _save_generic(account, "order", _order_payload(order))
        for row in history:
            _save_generic(account, "history", _history_payload(row))
        AccountControl.objects.update_or_create(
            account=account, defaults={"last_reconciled_at": now}
        )
    return "read_only_snapshot"


def observe_binance(account):
    """Backward-compatible entry point used by older callers."""
    return observe_external_account(account)
