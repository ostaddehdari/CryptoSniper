"""LBank Spot V2 adapter (HmacSHA256 signing)."""

import hashlib
import hmac
import secrets
from decimal import Decimal

from .adapters import (
    InvalidProviderResponse,
    Market,
    PermissionReport,
    ProviderRejectedError,
    Ticker,
    UnsafePermissionError,
    register_adapter,
)
from .spot_base import SpotAdapterBase, canonical_symbol, decimal, observed_at


@register_adapter
class LbankAdapter(SpotAdapterBase):
    code = "lbank"
    base_url = "https://api.lbank.info"

    @staticmethod
    def _provider_bool(value):
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "enabled", "on"}:
            return True
        if text in {"false", "0", "no", "disabled", "off"}:
            return False
        return None

    @staticmethod
    def _provider_symbol(symbol):
        return str(symbol).replace("/", "_").lower()

    def _request(self, method, path, params=None, signed=False):
        params = dict(params or {})
        headers = {"Accept": "application/json", "User-Agent": "CryptoSniper/0.24"}
        if signed:
            key, secret, _ = self._credentials()
            params.update(
                {
                    "api_key": key,
                    "echostr": secrets.token_hex(16),
                    "signature_method": "HmacSHA256",
                    "timestamp": str(self.clock()),
                }
            )
            prepared = self._query(dict(sorted(params.items())))
            digest = hashlib.md5(prepared.encode(), usedforsecurity=False).hexdigest().upper()
            params["sign"] = hmac.new(secret.encode(), digest.encode(), hashlib.sha256).hexdigest()
            headers.update(
                {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "timestamp": params["timestamp"],
                    "signature_method": params["signature_method"],
                    "echostr": params["echostr"],
                }
            )
        encoded = self._query(params)
        body = encoded if method == "POST" else None
        url = self.base_url + path + (("?" + encoded) if encoded and method == "GET" else "")
        payload = self.transport.request(method, url, headers=headers, body=body, timeout=10)
        if not isinstance(payload, (dict, list)):
            raise InvalidProviderResponse("lbank_invalid_response")
        if isinstance(payload, dict):
            result = payload.get("result")
            rejected = result is False or str(result).lower() in {"false", "failed", "error"}
            error_code = payload.get("error_code")
            if rejected or error_code not in {None, 0, "0"}:
                code = str(error_code or "rejected")
                message = str(payload.get("msg") or payload.get("message") or "request rejected")[:160]
                error = ProviderRejectedError(f"LBank code {code}: {message}")
                error.code = f"lbank_{code}"
                raise error
        return payload.get("data", payload) if isinstance(payload, dict) else payload

    def validate_credentials(self):
        payload = self._request("POST", "/v2/supplement/api_Restrictions.do", signed=True)
        if not isinstance(payload, dict):
            raise InvalidProviderResponse("lbank_invalid_permissions")
        can_withdraw = self._provider_bool(payload.get("enableWithdrawals"))
        can_read = self._provider_bool(payload.get("enableReading"))
        can_trade = self._provider_bool(payload.get("enableSpotTrading"))
        ip_restricted = self._provider_bool(payload.get("ipRestrict"))
        if can_withdraw is True:
            raise UnsafePermissionError("کلید LBank دارای مجوز برداشت است.")
        return PermissionReport(
            can_read=can_read is True,
            can_trade_spot=can_trade is True,
            can_trade_margin=False,
            can_withdraw=False if can_withdraw is False else None,
            ip_restricted=ip_restricted,
            account_reference="lbank-api-key",
            notes=("LBank Spot V2؛ Futures غیرفعال است.",),
        )

    def fetch_balance(self):
        payload = self._request("POST", "/v2/supplement/user_info_account.do", signed=True)
        return self._balance_rows(payload.get("balances", []))

    def fetch_markets(self):
        payload = self._request("GET", "/v2/accuracy.do")
        rows = payload if isinstance(payload, list) else payload.get("data", [])
        markets = []
        for item in rows:
            raw, meta = item.get("symbol", ""), item
            try:
                symbol = canonical_symbol(str(raw).replace("_", ""))
            except InvalidProviderResponse:
                continue
            base, quote = symbol.split("/", 1)
            markets.append(
                Market(
                    symbol=symbol,
                    base_asset=base,
                    quote_asset=quote,
                    market_type="spot",
                    min_amount=self._optional(meta.get("minOrderAmount")),
                    amount_step=self._step(meta.get("quantityAccuracy")),
                    price_step=self._step(meta.get("priceAccuracy")),
                    min_notional=self._optional(meta.get("minOrderAmount")),
                    max_leverage=Decimal("1"),
                    active=meta.get("status", "1") not in {"0", 0},
                    metadata={"provider_symbol": raw},
                )
            )
        return markets

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
            "GET", "/v2/ticker/24hr.do", {"symbol": self._provider_symbol(symbol)}
        )
        item = payload[0] if isinstance(payload, list) else payload
        ticker = item.get("ticker", item)
        return Ticker(
            symbol.upper(),
            decimal(ticker.get("latest", ticker.get("last"))),
            observed_at(item.get("timestamp")),
        )

    def fetch_orderbook(self, symbol):
        payload = self._request(
            "GET", "/v2/depth.do", {"symbol": self._provider_symbol(symbol), "size": 5}
        )
        return {
            "symbol": symbol.upper(),
            "bids": [(decimal(p), decimal(q)) for p, q in payload.get("bids", [])[:5]],
            "asks": [(decimal(p), decimal(q)) for p, q in payload.get("asks", [])[:5]],
            "observed_at": observed_at(payload.get("timestamp")),
        }

    def _lbank_order(self, item, fallback=None):
        fallback = fallback or {}
        normalized = {
            "orderId": item.get("order_id", item.get("orderId", item.get("id", ""))),
            "clientOrderId": item.get(
                "custom_id", item.get("clientOrderId", fallback.get("client_order_id", ""))
            ),
            "symbol": str(
                item.get("symbol", self._provider_symbol(fallback.get("symbol", "")))
            ).replace("_", ""),
            "side": item.get("type", fallback.get("side", "buy")),
            "type": fallback.get("order_type", "limit"),
            "quantity": item.get("amount", item.get("origQty", fallback.get("amount"))),
            "price": item.get("price", fallback.get("price")),
            "executedQty": item.get("deal_amount", item.get("accAmt", 0)),
            "avgPrice": item.get("avg_price", item.get("avgPrice")),
            "status": item.get("status", "0"),
            "time": item.get("create_time", item.get("time")),
        }
        return self._order(normalized, fallback)

    def place_order(self, **intent):
        order_type = str(intent["order_type"]).lower()
        payload = self._request(
            "POST",
            "/v2/supplement/create_order.do",
            {
                "symbol": self._provider_symbol(intent["symbol"]),
                "type": str(intent["side"]).lower()
                if order_type == "limit"
                else str(intent["side"]).lower() + "_market",
                "amount": str(intent["amount"]),
                "price": str(intent.get("price") or ""),
                "custom_id": str(intent["client_order_id"]),
            },
            signed=True,
        )
        item = payload.get("data", payload) if isinstance(payload, dict) else payload
        return self._lbank_order(item, intent)

    def cancel_order(self, order_id):
        payload = self._request("POST", "/v2/cancel_order.do", {"order_id": order_id}, signed=True)
        return self._lbank_order(payload)

    def fetch_order(self, order_id):
        payload = self._request("POST", "/v2/orders_info.do", {"order_id": order_id}, signed=True)
        rows = payload.get("orders", payload if isinstance(payload, list) else [])
        if not rows:
            raise InvalidProviderResponse("lbank_order_not_found")
        return self._lbank_order(rows[0])

    def fetch_open_orders(self):
        payload = self._request("POST", "/v2/orders_info_no_deal.do", signed=True)
        rows = payload.get("orders", payload if isinstance(payload, list) else [])
        return [self._lbank_order(item) for item in rows]

    def fetch_trade_history(self):
        payload = self._request(
            "POST",
            "/v2/supplement/orders_info_history.do",
            {"current_page": 1, "page_length": 100},
            signed=True,
        )
        return payload.get("orders", payload if isinstance(payload, list) else [])
