from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from threading import Lock
from uuid import uuid4

from django.utils import timezone


class AdapterError(Exception):
    code = "adapter_error"


class AuthenticationError(AdapterError):
    code = "authentication_error"


class UnsafePermissionError(AdapterError):
    code = "unsafe_permissions"


class UnsupportedOperationError(AdapterError):
    code = "unsupported_operation"


class InvalidProviderResponse(AdapterError):
    code = "invalid_provider_response"


class OrderStatus(StrEnum):
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class PermissionReport:
    can_read: bool
    can_trade_spot: bool
    can_trade_margin: bool
    can_withdraw: bool | None
    ip_restricted: bool | None
    account_reference: str = ""
    notes: tuple[str, ...] = ()

    @property
    def safe_for_trading(self):
        return (
            self.can_read
            and bool(self.can_trade_spot or self.can_trade_margin)
            and self.can_withdraw is False
        )


@dataclass(frozen=True)
class Balance:
    asset: str
    free: Decimal
    locked: Decimal

    @property
    def total(self):
        return self.free + self.locked


@dataclass(frozen=True)
class Market:
    symbol: str
    base_asset: str
    quote_asset: str
    market_type: str
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    amount_step: Decimal | None = None
    price_step: Decimal | None = None
    min_notional: Decimal | None = None
    max_leverage: Decimal = Decimal("1")
    maker_fee: Decimal | None = None
    taker_fee: Decimal | None = None
    active: bool = True
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Ticker:
    symbol: str
    price: Decimal
    observed_at: datetime


@dataclass(frozen=True)
class Order:
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    amount: Decimal
    price: Decimal | None
    filled_amount: Decimal
    average_price: Decimal | None
    status: OrderStatus
    created_at: datetime


class ExchangeAdapter(ABC):
    code: str

    def __init__(self, credentials=None, environment="paper"):
        self.credentials = credentials or {}
        self.environment = environment

    @abstractmethod
    def validate_credentials(self) -> PermissionReport:
        raise NotImplementedError

    @abstractmethod
    def fetch_balance(self) -> list[Balance]:
        raise NotImplementedError

    @abstractmethod
    def fetch_markets(self) -> list[Market]:
        raise NotImplementedError

    @abstractmethod
    def fetch_ticker(self, symbol: str) -> Ticker:
        raise NotImplementedError

    @abstractmethod
    def fetch_orderbook(self, symbol: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def fetch_max_leverage(self, symbol: str) -> Decimal:
        raise NotImplementedError

    @abstractmethod
    def place_order(self, **intent) -> Order:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: str) -> Order:
        raise NotImplementedError

    @abstractmethod
    def edit_order(self, order_id: str, **changes) -> Order:
        raise NotImplementedError

    @abstractmethod
    def fetch_order(self, order_id: str) -> Order:
        raise NotImplementedError

    @abstractmethod
    def fetch_open_orders(self) -> list[Order]:
        raise NotImplementedError

    @abstractmethod
    def fetch_positions(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def fetch_trade_history(self) -> list[dict]:
        raise NotImplementedError


class SimulatorAdapter(ExchangeAdapter):
    code = "simulator"
    _prices = {"BTC/USDT": Decimal("65000"), "ETH/USDT": Decimal("3500")}

    def __init__(self, credentials=None, environment="paper"):
        super().__init__(credentials, environment)
        self._lock = Lock()
        self._orders = {}

    def validate_credentials(self):
        return PermissionReport(
            can_read=True,
            can_trade_spot=True,
            can_trade_margin=True,
            can_withdraw=False,
            ip_restricted=True,
            account_reference="paper-account",
            notes=("هیچ درخواست خارجی ارسال نمی‌شود.",),
        )

    def fetch_balance(self):
        return [
            Balance("USDT", Decimal("10000"), Decimal("0")),
            Balance("BTC", Decimal("0.05"), Decimal("0")),
            Balance("ETH", Decimal("1.25"), Decimal("0")),
        ]

    def fetch_markets(self):
        common = {
            "quote_asset": "USDT",
            "amount_step": Decimal("0.000001"),
            "price_step": Decimal("0.01"),
            "min_notional": Decimal("10"),
            "maker_fee": Decimal("0.001"),
            "taker_fee": Decimal("0.001"),
        }
        return [
            Market(
                symbol="BTC/USDT",
                base_asset="BTC",
                market_type="spot",
                min_amount=Decimal("0.00001"),
                **common,
            ),
            Market(
                symbol="ETH/USDT",
                base_asset="ETH",
                market_type="spot",
                min_amount=Decimal("0.0001"),
                **common,
            ),
            Market(
                symbol="BTC/USDT",
                base_asset="BTC",
                market_type="margin",
                min_amount=Decimal("0.00001"),
                max_leverage=Decimal("3"),
                **common,
            ),
        ]

    def fetch_ticker(self, symbol):
        try:
            price = self._prices[symbol.upper()]
        except KeyError as error:
            raise UnsupportedOperationError("بازار در شبیه‌ساز موجود نیست.") from error
        return Ticker(symbol.upper(), price, timezone.now())

    def fetch_orderbook(self, symbol):
        ticker = self.fetch_ticker(symbol)
        spread = ticker.price * Decimal("0.0001")
        return {
            "symbol": ticker.symbol,
            "bids": [(ticker.price - spread, Decimal("1"))],
            "asks": [(ticker.price + spread, Decimal("1"))],
            "observed_at": ticker.observed_at,
        }

    def fetch_max_leverage(self, symbol):
        values = [market.max_leverage for market in self.fetch_markets() if market.symbol == symbol]
        if not values:
            raise UnsupportedOperationError("بازار در شبیه‌ساز موجود نیست.")
        return max(values)

    def place_order(self, **intent):
        required = {"client_order_id", "symbol", "side", "order_type", "amount"}
        if required - set(intent):
            raise ValueError("Order intent is incomplete.")
        amount = Decimal(str(intent["amount"]))
        if amount <= 0 or intent["side"] not in {"buy", "sell"}:
            raise ValueError("Order amount or side is invalid.")
        client_order_id = str(intent["client_order_id"])
        with self._lock:
            for order in self._orders.values():
                if order.client_order_id == client_order_id:
                    return order
            price = Decimal(str(intent.get("price") or self.fetch_ticker(intent["symbol"]).price))
            market_order = intent["order_type"] == "market"
            order = Order(
                order_id="sim-" + uuid4().hex,
                client_order_id=client_order_id,
                symbol=str(intent["symbol"]).upper(),
                side=intent["side"],
                order_type=intent["order_type"],
                amount=amount,
                price=price,
                filled_amount=amount if market_order else Decimal("0"),
                average_price=price if market_order else None,
                status=OrderStatus.FILLED if market_order else OrderStatus.OPEN,
                created_at=timezone.now(),
            )
            self._orders[order.order_id] = order
            return order

    def cancel_order(self, order_id):
        order = self.fetch_order(order_id)
        if order.status != OrderStatus.OPEN:
            return order
        cancelled = Order(**{**order.__dict__, "status": OrderStatus.CANCELLED})
        self._orders[order_id] = cancelled
        return cancelled

    def edit_order(self, order_id, **changes):
        order = self.fetch_order(order_id)
        if order.status != OrderStatus.OPEN:
            raise UnsupportedOperationError("فقط سفارش باز قابل ویرایش است.")
        allowed = {"amount", "price"}
        if set(changes) - allowed:
            raise ValueError("Unsupported order changes.")
        values = order.__dict__.copy()
        for key, value in changes.items():
            values[key] = Decimal(str(value))
        edited = Order(**values)
        self._orders[order_id] = edited
        return edited

    def fetch_order(self, order_id):
        try:
            return self._orders[order_id]
        except KeyError as error:
            raise UnsupportedOperationError("سفارش شبیه‌ساز پیدا نشد.") from error

    def fetch_open_orders(self):
        return [order for order in self._orders.values() if order.status == OrderStatus.OPEN]

    def fetch_positions(self):
        return []

    def fetch_trade_history(self):
        return [
            order.__dict__.copy()
            for order in self._orders.values()
            if order.status == OrderStatus.FILLED
        ]


_registry = {SimulatorAdapter.code: SimulatorAdapter}


def register_adapter(adapter_class):
    if not issubclass(adapter_class, ExchangeAdapter) or not adapter_class.code:
        raise TypeError("Adapter must implement ExchangeAdapter and define a code.")
    _registry[adapter_class.code] = adapter_class
    return adapter_class


def get_adapter(code, *, credentials=None, environment="paper"):
    try:
        adapter_class = _registry[code]
    except KeyError as error:
        raise UnsupportedOperationError(f"Adapter {code!r} is not registered.") from error
    return adapter_class(credentials=credentials, environment=environment)


# Load built-in provider registrations after the base contract is defined.
from . import binance as _binance  # noqa: E402, F401
