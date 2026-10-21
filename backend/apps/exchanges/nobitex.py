"""Nobitex Spot adapter using the official token-authenticated API."""

import json
from decimal import Decimal

from .adapters import (
    AuthenticationError,
    Balance,
    InvalidProviderResponse,
    Market,
    Order,
    OrderStatus,
    PermissionReport,
    ProviderRejectedError,
    Ticker,
    UnsupportedOperationError,
    register_adapter,
)
from .spot_base import SpotAdapterBase, canonical_symbol, decimal, observed_at, provider_symbol


@register_adapter
class NobitexAdapter(SpotAdapterBase):
    code = "nobitex"
    base_url = "https://apiv2.nobitex.ir"
    private_url = "https://api.nobitex.ir"
    sandbox_url = "https://testnetapi.nobitex.ir"

    def _token(self):
        token = str(self.credentials.get("api_key", "")).strip().strip('"').strip("'")
        if token.lower().startswith("token "):
            token = token[6:].strip()
        if not token:
            raise AuthenticationError("Token نوبیتکس لازم است.")
        return token

    def _request(self, method, path, params=None, signed=False):
        headers = {"Accept": "application/json", "User-Agent": "CryptoSniper/0.24"}
        body = None
        query = ""
        if signed:
            headers["Authorization"] = "Token " + self._token()
        if method in {"GET", "DELETE"}:
            query = self._query(params)
        elif params is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(params, separators=(",", ":"))
        if self.environment == "sandbox":
            base = self.sandbox_url
        elif signed:
            base = self.private_url
        else:
            base = self.base_url
        payload = self.transport.request(
            method,
            base + path + (("?" + query) if query else ""),
            headers=headers,
            body=body,
            timeout=10,
        )
        if not isinstance(payload, dict):
            raise InvalidProviderResponse("nobitex_invalid_response")
        if str(payload.get("status", "")).lower() == "failed":
            code = str(payload.get("code") or payload.get("errorCode") or "rejected")[:80]
            message = str(
                payload.get("message")
                or payload.get("error")
                or payload.get("detail")
                or "request rejected"
            )[:160]
            error = ProviderRejectedError(f"Nobitex code {code}: {message}")
            error.code = f"nobitex_{code}"
            raise error
        return payload

    def validate_credentials(self):
        payload = self._request("GET", "/users/wallets/list", signed=True)
        if not isinstance(payload.get("wallets"), list):
            raise InvalidProviderResponse("nobitex_invalid_wallets")
        sandbox = self.environment == "sandbox"
        no_withdrawal = sandbox or self.credentials.get("no_withdrawal_confirmed") == "true"
        return PermissionReport(
            can_read=True,
            can_trade_spot=True,
            can_trade_margin=False,
            can_withdraw=False if no_withdrawal else None,
            ip_restricted=self.credentials.get("ip_restricted_confirmed") == "true",
            account_reference=str(payload.get("profile", "nobitex")),
            notes=(
                "Live write تا اثبات کلید بدون برداشت مسدود است."
                if not no_withdrawal
                else "محیط رسمی آزمایشی Nobitex؛ سرمایه واقعی استفاده نمی‌شود.",
            ),
        )

    def fetch_balance(self):
        payload = self._request("GET", "/users/wallets/list", signed=True)
        rows = payload.get("wallets", [])
        result = []
        for item in rows:
            total = decimal(item.get("balance", 0), allow_zero=True)
            blocked = decimal(item.get("blockedBalance", 0), allow_zero=True)
            free = decimal(item.get("activeBalance", total - blocked), allow_zero=True)
            balance = Balance(str(item.get("currency", "")).upper(), free, blocked)
            if balance.asset and balance.total:
                result.append(balance)
        return result

    def fetch_markets(self):
        payload = self._request("GET", "/v3/orderbook/all")
        markets = []
        for raw_symbol, item in payload.items():
            if raw_symbol == "status" or not isinstance(item, dict):
                continue
            try:
                symbol = canonical_symbol(raw_symbol)
            except InvalidProviderResponse:
                continue
            base, quote = symbol.split("/", 1)
            markets.append(
                Market(
                    symbol=symbol,
                    base_asset=base,
                    quote_asset=quote,
                    market_type="spot",
                    max_leverage=Decimal("1"),
                    active=True,
                    metadata={
                        "provider_symbol": raw_symbol,
                        "precision_status": "not_reported_by_orderbook",
                    },
                )
            )
        return markets

    def fetch_ticker(self, symbol):
        payload = self._request("GET", "/v3/orderbook/" + provider_symbol(symbol))
        return Ticker(
            symbol.upper(),
            decimal(payload["lastTradePrice"]),
            observed_at(payload.get("lastUpdate")),
        )

    def fetch_orderbook(self, symbol):
        payload = self._request("GET", "/v3/orderbook/" + provider_symbol(symbol))
        try:
            return {
                "symbol": symbol.upper(),
                "bids": [(decimal(p), decimal(q)) for p, q in payload["bids"][:5]],
                "asks": [(decimal(p), decimal(q)) for p, q in payload["asks"][:5]],
                "observed_at": observed_at(payload.get("lastUpdate")),
            }
        except (KeyError, TypeError, ValueError) as error:
            raise InvalidProviderResponse("nobitex_invalid_orderbook") from error

    @staticmethod
    def _nobitex_order(item, fallback=None):
        fallback = fallback or {}
        symbol = fallback.get("symbol") or canonical_symbol(
            "".join(
                [
                    str(item.get("srcCurrency", "")),
                    str(item.get("dstCurrency", "")),
                ]
            )
        )
        status = str(item.get("status", "Active")).lower()
        mapped = (
            OrderStatus.FILLED
            if status in {"done", "filled"}
            else OrderStatus.CANCELLED
            if status in {"canceled", "cancelled"}
            else OrderStatus.PARTIAL
            if decimal(item.get("matchedAmount", 0), allow_zero=True) > 0
            else OrderStatus.OPEN
        )
        amount = decimal(item.get("amount", fallback.get("amount")))
        filled = decimal(item.get("matchedAmount", 0), allow_zero=True)
        return Order(
            order_id=str(item.get("id", item.get("order", ""))),
            client_order_id=str(item.get("clientOrderId", fallback.get("client_order_id", ""))),
            symbol=symbol.upper(),
            side=str(item.get("type", fallback.get("side", "buy"))).lower(),
            order_type=str(item.get("execution", fallback.get("order_type", "limit"))).lower(),
            amount=amount,
            price=decimal(item.get("price", fallback.get("price"))),
            filled_amount=filled,
            average_price=decimal(item.get("averagePrice", 0), allow_zero=True) or None,
            status=mapped,
            created_at=observed_at(item.get("created_at")),
        )

    def place_order(self, **intent):
        base, quote = intent["symbol"].split("/", 1)
        if str(intent["order_type"]).lower() != "limit":
            raise UnsupportedOperationError("Nobitex در این اتصال فقط Limit ایمن می‌پذیرد.")
        payload = self._request(
            "POST",
            "/market/orders/add",
            {
                "type": str(intent["side"]).lower(),
                "srcCurrency": base.lower(),
                "dstCurrency": quote.lower(),
                "amount": str(intent["amount"]),
                "price": str(intent["price"]),
                "execution": "limit",
                "clientOrderId": str(intent["client_order_id"]),
            },
            signed=True,
        )
        return self._nobitex_order(payload.get("order", payload), intent)

    def cancel_order(self, order_id):
        payload = self._request(
            "POST",
            "/market/orders/update-status",
            {"order": order_id, "status": "canceled"},
            signed=True,
        )
        return self._nobitex_order(payload.get("order", payload))

    def fetch_order(self, order_id):
        payload = self._request("POST", "/market/orders/status", {"id": order_id}, signed=True)
        return self._nobitex_order(payload.get("order", payload))

    def fetch_open_orders(self):
        payload = self._request(
            "GET", "/market/orders/list", {"status": "active", "details": 2}, signed=True
        )
        return [self._nobitex_order(item) for item in payload.get("orders", [])]

    def fetch_trade_history(self):
        payload = self._request("GET", "/market/trades/list", signed=True)
        return payload.get("trades", [])
