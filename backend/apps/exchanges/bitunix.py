"""Bitunix Spot V1 adapter using the official double-SHA256 signature."""

import hashlib
import json
import secrets
from decimal import Decimal

from .adapters import (
    InvalidProviderResponse,
    Market,
    PermissionReport,
    ProviderRejectedError,
    Ticker,
    UnsupportedOperationError,
    register_adapter,
)
from .spot_base import SpotAdapterBase, canonical_symbol, decimal, observed_at, provider_symbol


@register_adapter
class BitunixAdapter(SpotAdapterBase):
    code = "bitunix"
    base_url = "https://openapi.bitunix.com"

    def _request(self, method, path, params=None, signed=False):
        params = dict(params or {})
        headers = {"Accept": "application/json", "User-Agent": "CryptoSniper/0.23"}
        query = self._query(dict(sorted(params.items()))) if method == "GET" else ""
        body = (
            json.dumps(params, separators=(",", ":"), sort_keys=True)
            if method == "POST" and params
            else ""
        )
        if signed:
            key, secret, _ = self._credentials()
            nonce = secrets.token_hex(16)
            timestamp = str(self.clock())
            query_signature = (
                "".join(f"{k}={v}" for k, v in sorted(params.items())) if method == "GET" else ""
            )
            digest = hashlib.sha256(
                (nonce + timestamp + key + query_signature + body).encode()
            ).hexdigest()
            signature = hashlib.sha256((digest + secret).encode()).hexdigest()
            headers.update(
                {"api-key": key, "nonce": nonce, "timestamp": timestamp, "sign": signature}
            )
        if body:
            headers["Content-Type"] = "application/json"
        payload = self.transport.request(
            method,
            self.base_url + path + (("?" + query) if query else ""),
            headers=headers,
            body=body or None,
            timeout=10,
        )
        if not isinstance(payload, dict):
            raise InvalidProviderResponse("bitunix_invalid_payload")
        code = payload.get("code")
        if code not in {0, "0", None}:
            provider_code = str(code)
            provider_message = str(payload.get("msg") or "request rejected").strip()[:160]
            hints = {
                "403": "API key does not allow this operation.",
                "10003": "API key header is missing or empty.",
                "10004": "Server IP is not in the API-key whitelist.",
                "10005": "Bitunix rate limit reached.",
                "10006": "Requests are too frequent.",
                "10007": "Signature rejected; check API secret and signing input.",
                "10010": "Nonce format/length rejected.",
                "10011": "Server clock differs by more than 60 seconds.",
                "20001": "Market/symbol does not exist.",
                "20003": "Insufficient balance.",
            }
            hint = hints.get(provider_code, "Bitunix returned a definite provider rejection.")
            error = ProviderRejectedError(
                f"Bitunix code {provider_code}: {provider_message} {hint}"
            )
            error.code = f"bitunix_{provider_code}"
            raise error
        return payload.get("data", payload)

    def validate_credentials(self):
        payload = self._request("GET", "/api/spot/v1/user/account", signed=True)
        if not isinstance(payload, list):
            raise InvalidProviderResponse("bitunix_invalid_account")
        no_withdrawal = self.credentials.get("no_withdrawal_confirmed") == "true"
        return PermissionReport(
            can_read=True,
            can_trade_spot=True,
            can_trade_margin=False,
            can_withdraw=False if no_withdrawal else None,
            ip_restricted=self.credentials.get("ip_restricted_confirmed") == "true",
            account_reference="bitunix-spot",
            notes=("مجوز برداشت Bitunix با تأیید تنظیم کلید توسط کاربر ثبت شده است.",),
        )

    def fetch_balance(self):
        payload = self._request("GET", "/api/spot/v1/user/account", signed=True)
        return self._balance_rows(payload)

    def fetch_markets(self):
        rows = self._request("GET", "/api/spot/v1/common/coin_pair/list")
        if not isinstance(rows, list):
            raise InvalidProviderResponse("bitunix_invalid_markets")
        result = []
        for item in rows:
            try:
                symbol = canonical_symbol(
                    item.get("symbol", ""), item.get("base"), item.get("quote")
                )
            except InvalidProviderResponse:
                continue
            base, quote = symbol.split("/", 1)
            result.append(
                Market(
                    symbol=symbol,
                    base_asset=base,
                    quote_asset=quote,
                    market_type="spot",
                    min_amount=self._optional(item.get("minVolume")),
                    amount_step=self._step(item.get("basePrecision")),
                    price_step=self._step(item.get("quotePrecision")),
                    min_notional=self._optional(item.get("minPrice")),
                    max_leverage=Decimal("1"),
                    active=str(item.get("isOpen", "1")) == "1",
                    metadata={"provider_symbol": item.get("symbol", "")},
                )
            )
        return result

    @staticmethod
    def _optional(value):
        return None if value in {None, ""} else decimal(value, allow_zero=True)

    @staticmethod
    def _step(value):
        if value in {None, ""}:
            return None
        return Decimal(1).scaleb(-int(value))

    def fetch_ticker(self, symbol):
        payload = self._request(
            "GET", "/api/spot/v1/market/last_price", {"symbol": provider_symbol(symbol)}
        )
        price = payload.get("price", payload) if isinstance(payload, dict) else payload
        return Ticker(symbol.upper(), decimal(price), observed_at())

    def fetch_orderbook(self, symbol):
        payload = self._request(
            "GET", "/api/spot/v1/market/depth", {"symbol": provider_symbol(symbol), "precision": 8}
        )
        return {
            "symbol": symbol.upper(),
            "bids": [
                (decimal(row["price"]), decimal(row["volume"]))
                for row in payload.get("bids", [])[:5]
            ],
            "asks": [
                (decimal(row["price"]), decimal(row["volume"]))
                for row in payload.get("asks", [])[:5]
            ],
            "observed_at": observed_at(payload.get("ts")),
        }

    def _bitunix_order(self, item, fallback=None):
        fallback = fallback or {}
        return self._order(
            {
                "orderId": item.get("orderId", ""),
                "clientOrderId": fallback.get("client_order_id", ""),
                "symbol": item.get("symbol", provider_symbol(fallback.get("symbol", ""))),
                "side": "buy" if str(item.get("side", "2")) == "2" else "sell",
                "type": "market"
                if str(item.get("type", item.get("orderType", "1"))) == "2"
                else "limit",
                "quantity": item.get("volume", fallback.get("amount")),
                "price": item.get("price", fallback.get("price")),
                "executedQty": item.get("dealVolume", 0),
                "avgPrice": item.get("avgPrice"),
                "status": item.get("status", "1"),
                "time": item.get("ctime"),
            },
            fallback,
        )

    def place_order(self, **intent):
        payload = self._request(
            "POST",
            "/api/spot/v1/order/place_order",
            {
                "side": 2 if str(intent["side"]).lower() == "buy" else 1,
                "type": 2 if str(intent["order_type"]).lower() == "market" else 1,
                "volume": str(intent["amount"]),
                "price": str(intent.get("price") or "0"),
                "symbol": provider_symbol(intent["symbol"]),
            },
            signed=True,
        )
        return self._bitunix_order(payload, intent)

    def cancel_order(self, order_id):
        self._request(
            "POST",
            "/api/spot/v1/order/cancel",
            {"orderIdList": [{"orderId": str(order_id)}]},
            signed=True,
        )
        return self.fetch_order(order_id)

    def fetch_order(self, order_id):
        return self._bitunix_order(
            self._request(
                "GET", "/api/spot/v1/order/detail", {"orderId": str(order_id)}, signed=True
            )
        )

    def fetch_open_orders(self, symbol=None):
        if not symbol:
            raise UnsupportedOperationError(
                "Bitunix Spot requires symbol when querying current orders."
            )
        payload = self._request(
            "POST",
            "/api/spot/v1/order/pending/list",
            {"symbol": provider_symbol(symbol)},
            signed=True,
        )
        rows = payload.get("data", payload if isinstance(payload, list) else [])
        return [self._bitunix_order(item, {"symbol": symbol}) for item in rows]

    def fetch_trade_history(self, symbol=None):
        if not symbol:
            raise UnsupportedOperationError(
                "Bitunix Spot requires symbol when querying order history."
            )
        payload = self._request(
            "POST",
            "/api/spot/v1/order/history/page",
            {"page": 1, "pageSize": 100, "symbol": provider_symbol(symbol)},
            signed=True,
        )
        rows = payload.get("data", payload if isinstance(payload, list) else [])
        return rows if isinstance(rows, list) else []
