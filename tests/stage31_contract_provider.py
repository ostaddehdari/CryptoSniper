"""PostgreSQL-backed contract provider for tests ONLY. Never selects a real exchange."""

from datetime import timedelta
from decimal import Decimal

from apps.exchanges.adapters import Balance, Order, OrderStatus, PermissionReport, Ticker
from apps.operations.models import ExternalObservation
from django.db import transaction
from django.utils import timezone


class ReceiptProvider:
    def __init__(self, account_id):
        self.account_id = account_id

    def control(self):
        return ExternalObservation.objects.get(
            account_id=self.account_id, kind="s31-contract", external_id="control"
        )

    def validate_credentials(self):
        return PermissionReport(True, True, False, False, True)

    def fetch_ticker(self, symbol):
        c = self.control().payload
        if c.get("offline"):
            raise TimeoutError("contract feed outage")
        return Ticker(
            symbol, Decimal(c["price"]), timezone.now() - timedelta(seconds=c.get("age", 0))
        )

    def fetch_balance(self):
        return [
            Balance("BTC", Decimal(self.control().payload.get("free", "10")), Decimal(0)),
            Balance("USDT", Decimal("1000"), Decimal(0)),
        ]

    def receipt(self, row):
        p = row.payload
        filled = Decimal(p.get("filled", "0"))
        return Order(
            row.external_id,
            p["client"],
            p["symbol"],
            p["side"],
            "limit",
            Decimal(p["amount"]),
            Decimal(p["price"]),
            filled,
            Decimal(p["price"]) if filled else None,
            OrderStatus(p["status"]),
            row.observed_at,
        )

    def fetch_order(self, order_id):
        return self.receipt(
            ExternalObservation.objects.get(
                account_id=self.account_id, kind="s31-contract", external_id=order_id
            )
        )

    def fetch_open_orders(self):
        return [
            self.receipt(r)
            for r in ExternalObservation.objects.filter(
                account_id=self.account_id, kind="s31-contract"
            ).exclude(external_id="control")
            if r.payload["status"] in {"open", "partial"}
        ]

    @transaction.atomic
    def place_order(self, **intent):
        c = ExternalObservation.objects.select_for_update().get(pk=self.control().pk)
        c.payload["writes"] = c.payload.get("writes", 0) + 1
        c.save()
        amount = Decimal(intent["amount"])
        ratio = Decimal(c.payload.get("fill_ratio", "1"))
        row = ExternalObservation.objects.create(
            account_id=self.account_id,
            kind="s31-contract",
            external_id="receipt-" + intent["client_order_id"],
            payload={
                "client": intent["client_order_id"],
                "symbol": intent["symbol"],
                "side": intent["side"],
                "price": str(intent["price"]),
                "amount": str(amount),
                "filled": str(amount * ratio),
                "status": "filled" if ratio == 1 else "partial" if ratio else "open",
            },
        )
        receipt = self.receipt(row)
        # Timeout must follow a durable provider commit, outside this transaction.
        return receipt

    def cancel_order(self, order_id):
        row = ExternalObservation.objects.get(
            account_id=self.account_id, kind="s31-contract", external_id=order_id
        )
        row.payload["status"] = "cancelled"
        row.save()
        return self.receipt(row)


def install_contract_provider():
    from apps.exchanges import live_orders, reconciliation
    from apps.portfolio import live_management

    reconciliation.account_adapter = lambda account: ReceiptProvider(account.pk)
    live_management.account_adapter = reconciliation.account_adapter
    live_orders.get_account_credentials = lambda account: {"account_id": account.pk}
    live_orders.get_adapter = lambda code, credentials, environment: ReceiptProvider(
        credentials["account_id"]
    )
