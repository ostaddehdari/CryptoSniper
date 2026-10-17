"""Read-only Binance Spot snapshots. External assets/orders remain unmanaged.

API contract: https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/account
No POST/DELETE exchange endpoints, adoption or inferred position cost basis.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.audit import record_audit
from apps.exchanges.adapters import get_adapter
from apps.exchanges.models import Asset, BalanceSnapshot
from apps.exchanges.security import get_account_credentials

from .models import AccountControl, ExternalObservation


def _rows(payload, required):
    if not isinstance(payload, list) or len(payload) > 5000:
        raise ValidationError("پاسخ مشاهدهٔ صرافی معتبر یا محدود نیست.")
    if any(not isinstance(row, dict) or required - row.keys() for row in payload):
        raise ValidationError("پاسخ مشاهدهٔ صرافی ناقص است.")
    return payload


def observe_binance(account):
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
