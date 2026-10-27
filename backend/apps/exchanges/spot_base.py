"""Shared, fail-closed helpers for real Spot exchange adapters.

Provider modules own signing and response validation.  This module deliberately
does not retry writes: a timed-out order is an unknown outcome and must be
reconciled by client/exchange order id before any new submission.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.utils import timezone

from .adapters import (
    AuthenticationError,
    Balance,
    ExchangeAdapter,
    InvalidProviderResponse,
    Market,
    Order,
    OrderStatus,
    UnsupportedOperationError,
)


class JsonHttpTransport:
    """Small stdlib HTTPS transport whose exceptions never include signed URLs."""

    def request(self, method, url, headers=None, body=None, timeout=10):
        payload = body
        if isinstance(body, (dict, list)):
            payload = json.dumps(body, separators=(",", ":")).encode()
        elif isinstance(body, str):
            payload = body.encode()
        request = Request(url, data=payload, headers=headers or {}, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                raw = response.read()
        except HTTPError as error:
            if error.code in {401, 403}:
                raise AuthenticationError("صرافی اطلاعات اتصال را نپذیرفت.") from error
            raise InvalidProviderResponse(f"provider_http_{error.code}") from error
        except (URLError, TimeoutError) as error:
            raise InvalidProviderResponse("provider_connection_failed") from error
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise InvalidProviderResponse("provider_invalid_json") from error


def decimal(value, *, allow_zero=False):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise InvalidProviderResponse("provider_invalid_decimal") from error
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
        raise InvalidProviderResponse("provider_invalid_decimal")
    return number


def optional_decimal(value):
    if value in {None, ""}:
        return None
    return decimal(value, allow_zero=True)


def provider_symbol(symbol):
    return str(symbol).replace("/", "").replace("_", "").upper()


def canonical_symbol(value, base=None, quote=None):
    if base and quote:
        return f"{str(base).upper()}/{str(quote).upper()}"
    text = str(value).upper()
    for quote_name in ("USDT", "USDC", "BTC", "ETH", "IRT", "RLS"):
        if text.endswith(quote_name) and len(text) > len(quote_name):
            return f"{text[: -len(quote_name)]}/{quote_name}"
    raise InvalidProviderResponse("provider_symbol_not_canonical")


def observed_at(value=None):
    if value in {None, ""}:
        return timezone.now()
    try:
        number = int(value)
        if number > 10_000_000_000:
            number /= 1000
        return datetime.fromtimestamp(number, tz=UTC)
    except (ValueError, TypeError, OSError, OverflowError) as error:
        raise InvalidProviderResponse("provider_invalid_timestamp") from error


def order_status(value):
    normalized = str(value).lower().replace("_", "")
    if normalized in {"new", "open", "active", "0", "1", "unfilled"}:
        return OrderStatus.OPEN
    if normalized in {"partial", "partiallyfilled", "3", "partiallyfilledcancelled"}:
        return OrderStatus.PARTIAL
    if normalized in {"filled", "done", "completed", "2"}:
        return OrderStatus.FILLED
    if normalized in {"cancelled", "canceled", "4", "-1", "7"}:
        return OrderStatus.CANCELLED
    raise InvalidProviderResponse("provider_unknown_order_status")


class SpotAdapterBase(ExchangeAdapter):
    """Common Spot-only normalization; subclasses implement provider calls."""

    base_url = ""

    def __init__(self, credentials=None, environment="live", transport=None, clock=None):
        super().__init__(credentials, environment)
        self.transport = transport or JsonHttpTransport()
        self.clock = clock or (lambda: int(timezone.now().timestamp() * 1000))

    def _credentials(self, *, passphrase=False):
        key = self.credentials.get("api_key", "")
        secret = self.credentials.get("api_secret", "")
        phrase = self.credentials.get("passphrase", "")
        if not key or not secret or (passphrase and not phrase):
            raise AuthenticationError("اطلاعات کامل API لازم است.")
        return key, secret, phrase

    @staticmethod
    def _query(params):
        return urlencode(
            [(key, value) for key, value in (params or {}).items() if value is not None]
        )

    @staticmethod
    def _market_from_exchange_info(item):
        filters = {row.get("filterType"): row for row in item.get("filters", [])}
        lot = filters.get("LOT_SIZE", {})
        price_filter = filters.get("PRICE_FILTER", {})
        notional = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL", {})
        symbol = canonical_symbol(item.get("symbol"), item.get("baseAsset"), item.get("quoteAsset"))
        base, quote = symbol.split("/", 1)
        return Market(
            symbol=symbol,
            base_asset=base,
            quote_asset=quote,
            market_type="spot",
            min_amount=optional_decimal(lot.get("minQty")),
            max_amount=optional_decimal(lot.get("maxQty")),
            amount_step=optional_decimal(lot.get("stepSize")),
            price_step=optional_decimal(price_filter.get("tickSize")),
            min_notional=optional_decimal(notional.get("minNotional")),
            max_leverage=Decimal("1"),
            maker_fee=optional_decimal(item.get("makerFee")),
            taker_fee=optional_decimal(item.get("takerFee")),
            active=item.get("status", "TRADING") in {"TRADING", "ENABLED", "1", 1},
            metadata={"provider_symbol": item.get("symbol", "")},
        )

    @staticmethod
    def _balance_rows(rows):
        result = []
        for item in rows:
            balance = Balance(
                str(item.get("asset") or item.get("coin")).upper(),
                decimal(
                    item.get("free", item.get("usableAmt", item.get("balance", 0))), allow_zero=True
                ),
                decimal(
                    item.get("locked", item.get("freezeAmt", item.get("balanceLocked", 0))),
                    allow_zero=True,
                ),
            )
            if balance.total:
                result.append(balance)
        return result

    @staticmethod
    def _order(payload, fallback=None):
        fallback = fallback or {}
        symbol = canonical_symbol(
            payload.get("symbol", fallback.get("symbol", "")),
            payload.get("base"),
            payload.get("quote"),
        )
        amount = payload.get(
            "origQty", payload.get("quantity", payload.get("volume", fallback.get("amount")))
        )
        filled = payload.get(
            "executedQty", payload.get("dealVolume", payload.get("filledAmount", 0))
        )
        price = payload.get("price", fallback.get("price"))
        average = payload.get("avgPrice", payload.get("averagePrice"))
        fee_amount = optional_decimal(
            payload.get("commission", payload.get("fee", payload.get("filledFee")))
        )
        fee_asset = str(
            payload.get("commissionAsset", payload.get("feeAsset", payload.get("feeCurrency", "")))
        ).upper()
        quote = symbol.split("/", 1)[1]
        return Order(
            order_id=str(payload.get("orderId", payload.get("id", ""))),
            client_order_id=str(payload.get("clientOrderId", fallback.get("client_order_id", ""))),
            symbol=symbol,
            side=str(payload.get("side", fallback.get("side", "buy"))).lower(),
            order_type=str(payload.get("type", fallback.get("order_type", "limit"))).lower(),
            amount=decimal(amount),
            price=optional_decimal(price),
            filled_amount=decimal(filled, allow_zero=True),
            average_price=optional_decimal(average),
            status=order_status(payload.get("status", fallback.get("status", "open"))),
            created_at=observed_at(payload.get("time", payload.get("transactTime"))),
            fee_amount=fee_amount,
            fee_asset=fee_asset,
            fee_quote_value=fee_amount if fee_amount is not None and fee_asset == quote else None,
        )

    def fetch_max_leverage(self, symbol):
        return Decimal("1")

    def edit_order(self, order_id, **changes):
        raise UnsupportedOperationError(
            "ویرایش مستقیم سفارش پشتیبانی نمی‌شود؛ لغو و سفارش جدید لازم است."
        )

    def fetch_positions(self):
        return []
