"""Guarded real-money Bitunix round-trip smoke test.

This command intentionally has a hard USDT exposure ceiling, records both legs in LiveSpotOrder,
never retries an ambiguous write, and exits if no market can satisfy the configured ceiling.
"""

import time
import uuid
from decimal import Decimal, ROUND_DOWN

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.exchanges.adapters import AdapterError, OrderStatus, get_adapter
from apps.exchanges.models import ExchangeMarket, LiveSpotOrder, UserExchangeAccount
from apps.exchanges.security import get_account_credentials
from apps.operations.models import AccountControl, RecoveryIssue


def _floor_step(value, step):
    if not step:
        return value
    units = (value / step).to_integral_value(rounding=ROUND_DOWN)
    return units * step


def _balance_map(adapter):
    return {row.asset: row.total for row in adapter.fetch_balance()}


def _state(status):
    return {
        OrderStatus.OPEN: LiveSpotOrder.State.OPEN,
        OrderStatus.PARTIAL: LiveSpotOrder.State.PARTIAL,
        OrderStatus.FILLED: LiveSpotOrder.State.FILLED,
        OrderStatus.CANCELLED: LiveSpotOrder.State.CANCELLED,
    }[status]


class Command(BaseCommand):
    help = "Execute one tiny Bitunix Spot market buy then sell after a short hold."

    def add_arguments(self, parser):
        parser.add_argument("--account-id", type=int, required=True)
        parser.add_argument("--max-usdt", type=Decimal, default=Decimal("1.00"))
        parser.add_argument("--hold-seconds", type=int, default=2)
        parser.add_argument("--confirm", required=True)

    def handle(self, *args, **options):
        if options["confirm"] != "REAL_MONEY":
            raise CommandError("--confirm REAL_MONEY is required.")
        max_usdt = Decimal(options["max_usdt"])
        if max_usdt <= 0 or max_usdt > Decimal("5"):
            raise CommandError("--max-usdt must be > 0 and <= 5 USDT.")
        hold = max(0, min(int(options["hold_seconds"]), 10))

        if not settings.LIVE_TRADING_ENABLED:
            raise CommandError("LIVE_TRADING_ENABLED=false; refusing a real order.")

        account = (
            UserExchangeAccount.objects.select_related("exchange", "owner")
            .get(pk=options["account_id"])
        )
        if account.exchange.adapter_code != "bitunix" or account.environment != "live":
            raise CommandError("This smoke test is intentionally Bitunix-live only.")
        if (
            account.status != "connected"
            or not account.trading_enabled
            or account.permissions.get("can_trade_spot") is not True
            or account.permissions.get("can_withdraw") is not False
        ):
            raise CommandError("Bitunix account is not in safe connected Read+Spot/no-withdraw state.")
        control, _ = AccountControl.objects.get_or_create(account=account)
        if control.paused:
            raise CommandError("Account is paused in Operations.")
        if RecoveryIssue.objects.filter(account=account, resolved=False).exists():
            raise CommandError("Unresolved recovery issues exist; refusing real smoke trade.")

        adapter = get_adapter(
            "bitunix",
            credentials=get_account_credentials(account),
            environment="live",
        )
        permission = adapter.validate_credentials()
        if not permission.safe_for_trading:
            raise CommandError("Provider permission validation is not safe for trading.")

        provider_markets = [
            row for row in adapter.fetch_markets()
            if row.active and row.quote_asset == "USDT" and row.min_amount and row.base_asset not in {"USDT", "USDC"}
        ]

        # Prefer liquid/high-price assets. Numeric volume therefore remains small even if a
        # provider interprets market-order volume differently across API versions.
        preferred = ["SOL", "ETH", "BNB", "LTC", "BTC"]
        provider_markets.sort(
            key=lambda row: (
                preferred.index(row.base_asset) if row.base_asset in preferred else 999,
                row.base_asset,
            )
        )

        candidate = None
        smallest_seen = None
        for market in provider_markets[:120]:
            try:
                ticker = adapter.fetch_ticker(market.symbol)
            except AdapterError:
                continue
            price = ticker.price
            if price < Decimal("1"):
                continue
            amount = _floor_step(max(market.min_amount, market.amount_step or Decimal("0")), market.amount_step)
            if amount <= 0:
                continue
            estimated = amount * price
            if smallest_seen is None or estimated < smallest_seen[0]:
                smallest_seen = (estimated, market.symbol, amount, price)
            # Exposure is bounded under both common interpretations of Bitunix market volume:
            # base quantity (amount*price) and quote amount (numeric amount).
            if estimated <= max_usdt and amount <= max_usdt:
                candidate = (market, amount, price, estimated)
                break

        if not candidate:
            extra = ""
            if smallest_seen:
                extra = (
                    f" Smallest candidate seen: {smallest_seen[1]} "
                    f"estimated={smallest_seen[0]} USDT."
                )
            raise CommandError(
                f"No Bitunix market satisfies the {max_usdt} USDT safety ceiling.{extra} "
                "No order was sent."
            )

        provider_market, amount, price, estimated = candidate
        db_market = ExchangeMarket.objects.filter(
            exchange=account.exchange,
            symbol=provider_market.symbol,
            market_type="spot",
            active=True,
        ).first()
        if not db_market:
            raise CommandError("Selected market is not synchronized in CryptoSniper DB.")

        before = _balance_map(adapter)
        base = provider_market.base_asset
        before_base = before.get(base, Decimal("0"))
        before_usdt = before.get("USDT", Decimal("0"))
        if before_usdt < estimated:
            raise CommandError(
                f"Insufficient USDT for smoke test: free total={before_usdt}, estimated={estimated}."
            )

        self.stdout.write(
            self.style.WARNING(
                f"REAL MONEY: buying {provider_market.symbol}; amount={amount}; "
                f"estimated_notional≈{estimated} USDT; hard ceiling={max_usdt} USDT"
            )
        )

        def create_log(side, requested_amount):
            key = uuid.uuid4()
            return LiveSpotOrder.objects.create(
                owner=account.owner,
                account=account,
                market=db_market,
                request_key=key,
                client_order_id=f"cs-smoke-{side}-{key.hex[:24]}",
                side=side,
                order_type="market",
                amount=requested_amount,
                price=None,
            )

        buy_log = create_log("buy", amount)
        try:
            receipt = adapter.place_order(
                client_order_id=buy_log.client_order_id,
                symbol=provider_market.symbol,
                side="buy",
                order_type="market",
                amount=amount,
                price=None,
            )
        except Exception as exc:
            buy_log.state = LiveSpotOrder.State.UNCERTAIN if isinstance(exc, (AdapterError, TimeoutError, OSError)) else LiveSpotOrder.State.FAILED
            buy_log.error_code = getattr(exc, "code", type(exc).__name__)[:50]
            buy_log.save(update_fields=("state", "error_code", "updated_at"))
            raise CommandError(
                f"BUY was not confirmed ({buy_log.error_code}). Do not retry automatically; inspect Bitunix."
            ) from exc

        buy_log.external_order_id = receipt.order_id
        buy_log.filled_amount = receipt.filled_amount
        buy_log.average_price = receipt.average_price
        buy_log.state = _state(receipt.status)
        buy_log.save()
        if receipt.status not in {OrderStatus.FILLED, OrderStatus.PARTIAL}:
            raise CommandError(
                f"BUY order exists but is {receipt.status}; order_id={receipt.order_id}. "
                "No sell was attempted."
            )

        time.sleep(hold)
        after_buy = _balance_map(adapter)
        acquired = max(Decimal("0"), after_buy.get(base, Decimal("0")) - before_base)
        acquired = _floor_step(acquired, provider_market.amount_step)
        if acquired <= 0:
            raise CommandError(
                f"BUY confirmed but no positive {base} balance delta was observed. "
                f"order_id={receipt.order_id}. No sell was attempted."
            )

        sell_log = create_log("sell", acquired)
        self.stdout.write(
            self.style.WARNING(
                f"REAL MONEY: selling acquired {base}={acquired} after {hold}s."
            )
        )
        try:
            sell_receipt = adapter.place_order(
                client_order_id=sell_log.client_order_id,
                symbol=provider_market.symbol,
                side="sell",
                order_type="market",
                amount=acquired,
                price=None,
            )
        except Exception as exc:
            sell_log.state = LiveSpotOrder.State.UNCERTAIN if isinstance(exc, (AdapterError, TimeoutError, OSError)) else LiveSpotOrder.State.FAILED
            sell_log.error_code = getattr(exc, "code", type(exc).__name__)[:50]
            sell_log.save(update_fields=("state", "error_code", "updated_at"))
            raise CommandError(
                f"SELL was not confirmed ({sell_log.error_code}). Residual {base} may remain; inspect Bitunix manually."
            ) from exc

        sell_log.external_order_id = sell_receipt.order_id
        sell_log.filled_amount = sell_receipt.filled_amount
        sell_log.average_price = sell_receipt.average_price
        sell_log.state = _state(sell_receipt.status)
        sell_log.save()

        time.sleep(1)
        final = _balance_map(adapter)
        final_base = final.get(base, Decimal("0"))
        final_usdt = final.get("USDT", Decimal("0"))
        residual = max(Decimal("0"), final_base - before_base)
        usdt_delta = final_usdt - before_usdt

        self.stdout.write(
            self.style.SUCCESS(
                "ROUNDTRIP COMPLETE "
                f"symbol={provider_market.symbol} buy_order={buy_log.external_order_id} "
                f"sell_order={sell_log.external_order_id} residual_{base}={residual} "
                f"USDT_delta={usdt_delta}"
            )
        )
        self.stdout.write(
            f"Recorded LiveSpotOrder ids: buy={buy_log.pk}, sell={sell_log.pk}. "
            "Fees/slippage can make USDT_delta negative."
        )
