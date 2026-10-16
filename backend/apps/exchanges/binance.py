import hashlib
import hmac
import json
import time
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from django.utils import timezone

from .adapters import (
    AuthenticationError,
    Balance,
    ExchangeAdapter,
    InvalidProviderResponse,
    Market,
    PermissionReport,
    Ticker,
    UnsafePermissionError,
    UnsupportedOperationError,
    register_adapter,
)


class JsonTransport:
    def request(self, method, url, headers=None, timeout=10):
        request = Request(url, headers=headers or {}, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                payload = response.read()
        except HTTPError as error:
            if error.code in {401, 403}:
                raise AuthenticationError("صرافی اطلاعات اتصال را نپذیرفت.") from error
            raise InvalidProviderResponse(f"Binance HTTP {error.code}") from error
        except (URLError, TimeoutError) as error:
            raise InvalidProviderResponse("ارتباط امن با Binance برقرار نشد.") from error
        try:
            return json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise InvalidProviderResponse("Binance پاسخ JSON معتبر نداد.") from error


@register_adapter
class BinanceAdapter(ExchangeAdapter):
    """Read/sync boundary for Binance Spot/Margin; order writes remain disabled in S03."""

    code = "binance"
    base_url = "https://api.binance.com"

    def __init__(self, credentials=None, environment="live", transport=None, clock=None):
        super().__init__(credentials, environment)
        self.transport = transport or JsonTransport()
        self.clock = clock or (lambda: int(time.time() * 1000))

    def _credentials(self):
        api_key = self.credentials.get("api_key", "")
        secret = self.credentials.get("api_secret", "")
        if not api_key or not secret:
            raise AuthenticationError("API Key و Secret لازم است.")
        return api_key, secret

    def _request(self, path, params=None, signed=False):
        params = dict(params or {})
        headers = {"Accept": "application/json", "User-Agent": "CryptoSniper/0.3"}
        if signed:
            api_key, secret = self._credentials()
            params.update({"timestamp": self.clock(), "recvWindow": 5000})
            query = urlencode(sorted(params.items()))
            signature = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
            query = f"{query}&signature={signature}"
            headers["X-MBX-APIKEY"] = api_key
        else:
            query = urlencode(params)
        url = self.base_url + path + ("?" + query if query else "")
        response = self.transport.request("GET", url, headers=headers, timeout=10)
        if not isinstance(response, (dict, list)):
            raise InvalidProviderResponse("ساختار پاسخ Binance معتبر نیست.")
        return response

    def validate_credentials(self):
        payload = self._request("/sapi/v1/account/apiRestrictions", signed=True)
        required = {"enableReading", "enableWithdrawals", "enableSpotAndMarginTrading"}
        if not isinstance(payload, dict) or required - set(payload):
            raise InvalidProviderResponse("پاسخ مجوزهای Binance ناقص است.")
        if payload["enableWithdrawals"] is True:
            raise UnsafePermissionError(
                "کلید دارای مجوز برداشت است؛ آن را غیرفعال و یک کلید فقط‌معامله بسازید."
            )
        can_trade = payload["enableSpotAndMarginTrading"] is True
        return PermissionReport(
            can_read=payload["enableReading"] is True,
            can_trade_spot=can_trade,
            can_trade_margin=can_trade and payload.get("enableMargin") is True,
            can_withdraw=False,
            ip_restricted=payload.get("ipRestrict"),
            account_reference=str(payload.get("createTime", "")),
            notes=("اعتبارسنجی فقط‌خواندنی انجام شد؛ ارسال سفارش در S03 غیرفعال است.",),
        )

    def fetch_balance(self):
        payload = self._request("/api/v3/account", signed=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("balances"), list):
            raise InvalidProviderResponse("پاسخ موجودی Binance ناقص است.")
        result = []
        for item in payload["balances"]:
            try:
                balance = Balance(
                    asset=str(item["asset"]).upper(),
                    free=Decimal(str(item["free"])),
                    locked=Decimal(str(item["locked"])),
                )
            except (KeyError, ValueError, TypeError) as error:
                raise InvalidProviderResponse("یک ردیف موجودی Binance نامعتبر است.") from error
            if balance.total:
                result.append(balance)
        return result

    def fetch_markets(self):
        payload = self._request("/api/v3/exchangeInfo")
        if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
            raise InvalidProviderResponse("پاسخ بازارهای Binance ناقص است.")
        markets = []
        for item in payload["symbols"]:
            if item.get("status") != "TRADING":
                continue
            filters = {value.get("filterType"): value for value in item.get("filters", [])}
            lot = filters.get("LOT_SIZE", {})
            price = filters.get("PRICE_FILTER", {})
            notional = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL", {})
            common = {
                "symbol": f"{item['baseAsset']}/{item['quoteAsset']}",
                "base_asset": item["baseAsset"],
                "quote_asset": item["quoteAsset"],
                "min_amount": self._decimal_or_none(lot.get("minQty")),
                "max_amount": self._decimal_or_none(lot.get("maxQty")),
                "amount_step": self._decimal_or_none(lot.get("stepSize")),
                "price_step": self._decimal_or_none(price.get("tickSize")),
                "min_notional": self._decimal_or_none(notional.get("minNotional")),
                "active": True,
                "metadata": {"provider_symbol": item.get("symbol", "")},
            }
            if item.get("isSpotTradingAllowed") is True:
                markets.append(Market(market_type="spot", **common))
            if item.get("isMarginTradingAllowed") is True:
                markets.append(Market(market_type="margin", max_leverage=Decimal("1"), **common))
        return markets

    @staticmethod
    def _decimal_or_none(value):
        if value in {None, ""}:
            return None
        try:
            return Decimal(str(value))
        except (ValueError, TypeError) as error:
            raise InvalidProviderResponse("Precision بازار Binance معتبر نیست.") from error

    @staticmethod
    def provider_symbol(symbol):
        return symbol.replace("/", "").upper()

    def fetch_ticker(self, symbol):
        payload = self._request("/api/v3/ticker/price", {"symbol": self.provider_symbol(symbol)})
        try:
            return Ticker(symbol.upper(), Decimal(str(payload["price"])), timezone.now())
        except (KeyError, ValueError, TypeError) as error:
            raise InvalidProviderResponse("پاسخ قیمت Binance معتبر نیست.") from error

    def fetch_orderbook(self, symbol):
        payload = self._request(
            "/api/v3/depth", {"symbol": self.provider_symbol(symbol), "limit": 5}
        )
        try:
            return {
                "symbol": symbol.upper(),
                "bids": [(Decimal(price), Decimal(amount)) for price, amount in payload["bids"]],
                "asks": [(Decimal(price), Decimal(amount)) for price, amount in payload["asks"]],
                "observed_at": timezone.now(),
            }
        except (KeyError, ValueError, TypeError) as error:
            raise InvalidProviderResponse("پاسخ دفتر سفارش Binance معتبر نیست.") from error

    def fetch_max_leverage(self, symbol):
        raise UnsupportedOperationError(
            "اهرم Margin باید از endpoint حساب و بازار انتخاب‌شده همگام شود."
        )

    def _writes_disabled(self):
        raise UnsupportedOperationError(
            "ارسال یا تغییر سفارش واقعی تا استیج موتور معامله غیرفعال است."
        )

    def place_order(self, **intent):
        return self._writes_disabled()

    def cancel_order(self, order_id):
        return self._writes_disabled()

    def edit_order(self, order_id, **changes):
        return self._writes_disabled()

    def fetch_order(self, order_id):
        raise UnsupportedOperationError("همگام‌سازی سفارش در استیج موتور معامله فعال می‌شود.")

    def fetch_open_orders(self):
        raise UnsupportedOperationError("همگام‌سازی سفارش در استیج موتور معامله فعال می‌شود.")

    def fetch_positions(self):
        raise UnsupportedOperationError("همگام‌سازی Position در استیج موتور معامله فعال می‌شود.")

    def fetch_trade_history(self):
        raise UnsupportedOperationError("تاریخچه معامله در استیج موتور معامله فعال می‌شود.")


def safe_request_path(url):
    """A diagnostic helper that intentionally excludes query strings and signatures."""
    return urlsplit(url).path
