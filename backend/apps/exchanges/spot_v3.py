"""WEEX and Ourbit Spot V3 adapters based on their official REST contracts."""

import base64
import hashlib
import hmac
import json

from .adapters import (
    InvalidProviderResponse,
    PermissionReport,
    ProviderRejectedError,
    Ticker,
    UnsafePermissionError,
    register_adapter,
)
from .spot_base import SpotAdapterBase, decimal, observed_at, provider_symbol


class V3SpotMixin:
    api_key_header = ""

    def _ensure(self, payload):
        if not isinstance(payload, (dict, list)):
            raise InvalidProviderResponse("provider_invalid_response")
        if isinstance(payload, dict) and payload.get("code") not in {None, 0, "0", "00000"}:
            code = str(payload.get("code"))[:80]
            message = str(payload.get("msg") or payload.get("message") or "request rejected")[:160]
            error = ProviderRejectedError(f"Provider code {code}: {message}")
            error.code = f"provider_{code}"
            raise error
        return payload.get("data", payload) if isinstance(payload, dict) else payload

    def fetch_balance(self):
        payload = self._ensure(self._request("GET", "/api/v3/account", signed=True))
        if not isinstance(payload, dict) or not isinstance(payload.get("balances"), list):
            raise InvalidProviderResponse("provider_invalid_balance")
        return self._balance_rows(payload["balances"])

    def validate_credentials(self):
        payload = self._ensure(self._request("GET", "/api/v3/account", signed=True))
        if not isinstance(payload, dict):
            raise InvalidProviderResponse("provider_invalid_permissions")
        provider_can_withdraw = payload.get("canWithdraw")
        permissions = {str(item).upper() for item in payload.get("permissions", [])}
        can_trade = payload.get("canTrade") is True or bool(
            permissions & {"SPOT", "SPOT_TRADING", "SPOT_DEAL_WRITE"}
        )
        if self.code == "ourbit":
            # Ourbit /api/v3/account documents account withdrawal capability, while API-key
            # withdrawal authority is a separate permission family (SPOT_WITHDRAW_WRITE).
            # The account endpoint does not expose the current key's full permission set.
            no_withdrawal = self.credentials.get("no_withdrawal_confirmed") == "true"
            can_withdraw = False if no_withdrawal else None
            ip_restricted = self.credentials.get("ip_restricted_confirmed") == "true"
            notes = (
                "Ourbit key is treated as no-withdraw only after the operator explicitly confirms "
                "SPOT_WITHDRAW_WRITE is disabled in API Management.",
            )
        else:
            if provider_can_withdraw is True:
                raise UnsafePermissionError(
                    "کلید دارای مجوز برداشت است؛ کلید فقط Read+Spot بسازید."
                )
            can_withdraw = False if provider_can_withdraw is False else None
            ip_restricted = payload.get("ipRestricted")
            notes = ("Spot REST V3؛ Futures/Perpetual عمداً غیرفعال است.",)
        return PermissionReport(
            can_read=True,
            can_trade_spot=can_trade,
            can_trade_margin=False,
            can_withdraw=can_withdraw,
            ip_restricted=ip_restricted,
            account_reference=str(payload.get("uid", payload.get("accountType", ""))),
            notes=notes,
        )

    def fetch_markets(self):
        payload = self._ensure(self._request("GET", "/api/v3/exchangeInfo"))
        rows = payload.get("symbols", []) if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            raise InvalidProviderResponse("provider_invalid_markets")
        return [self._market_from_exchange_info(item) for item in rows]

    def fetch_ticker(self, symbol):
        payload = self._ensure(
            self._request("GET", "/api/v3/ticker/price", {"symbol": provider_symbol(symbol)})
        )
        try:
            return Ticker(
                symbol.upper(), decimal(payload["price"]), observed_at(payload.get("time"))
            )
        except (KeyError, TypeError) as error:
            raise InvalidProviderResponse("provider_invalid_ticker") from error

    def fetch_orderbook(self, symbol):
        payload = self._ensure(
            self._request("GET", "/api/v3/depth", {"symbol": provider_symbol(symbol), "limit": 5})
        )
        try:
            return {
                "symbol": symbol.upper(),
                "bids": [(decimal(p), decimal(q)) for p, q in payload["bids"]],
                "asks": [(decimal(p), decimal(q)) for p, q in payload["asks"]],
                "observed_at": observed_at(payload.get("time")),
            }
        except (KeyError, TypeError, ValueError) as error:
            raise InvalidProviderResponse("provider_invalid_orderbook") from error

    def place_order(self, **intent):
        body = {
            "symbol": provider_symbol(intent["symbol"]),
            "side": str(intent["side"]).upper(),
            "type": str(intent["order_type"]).upper(),
            "quantity": str(intent["amount"]),
            "newClientOrderId": str(intent["client_order_id"]),
        }
        if body["type"] == "LIMIT":
            body.update({"price": str(intent["price"]), "timeInForce": "GTC"})
        payload = self._ensure(self._request("POST", "/api/v3/order", body, signed=True))
        merged = {**body, **payload, "status": payload.get("status", "open")}
        return self._order(merged, intent)

    def cancel_order(self, order_id):
        params = {"orderId": str(order_id)}
        payload = self._ensure(self._request("DELETE", "/api/v3/order", params, signed=True))
        return self._order(payload)

    def fetch_order(self, order_id):
        payload = self._ensure(
            self._request("GET", "/api/v3/order", {"orderId": str(order_id)}, signed=True)
        )
        return self._order(payload)

    def fetch_open_orders(self):
        payload = self._ensure(self._request("GET", "/api/v3/openOrders", signed=True))
        if not isinstance(payload, list):
            raise InvalidProviderResponse("provider_invalid_orders")
        return [self._order(item) for item in payload]

    def fetch_trade_history(self):
        payload = self._ensure(self._request("GET", "/api/v3/allOrders", signed=True))
        if not isinstance(payload, list):
            raise InvalidProviderResponse("provider_invalid_history")
        return payload


@register_adapter
class WeexAdapter(V3SpotMixin, SpotAdapterBase):
    code = "weex"
    base_url = "https://api-spot.weex.com"

    def _request(self, method, path, params=None, signed=False):
        params = dict(params or {})
        headers = {"Accept": "application/json", "User-Agent": "CryptoSniper/0.24"}
        query = ""
        body = ""
        if method in {"GET", "DELETE"}:
            query = self._query(params)
        elif params:
            body = json.dumps(params, separators=(",", ":"))
            headers["Content-Type"] = "application/json"
        if signed:
            key, secret, phrase = self._credentials(passphrase=True)
            timestamp = str(self.clock())
            suffix = ("?" + query) if query else ""
            message = timestamp + method + path + suffix + body
            signature = base64.b64encode(
                hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()
            ).decode()
            headers.update(
                {
                    "ACCESS-KEY": key,
                    "ACCESS-SIGN": signature,
                    "ACCESS-TIMESTAMP": timestamp,
                    "ACCESS-PASSPHRASE": phrase,
                }
            )
        url = self.base_url + path + (("?" + query) if query else "")
        return self.transport.request(method, url, headers=headers, body=body or None, timeout=10)


@register_adapter
class OurbitAdapter(V3SpotMixin, SpotAdapterBase):
    code = "ourbit"
    base_url = "https://api.ourbit.com"

    def _request(self, method, path, params=None, signed=False):
        params = dict(params or {})
        headers = {"Accept": "application/json", "User-Agent": "CryptoSniper/0.24"}
        if signed:
            key, secret, _ = self._credentials()
            params.setdefault("recvWindow", 5000)
            params.setdefault("timestamp", self.clock())
            unsigned = self._query(params)
            params["signature"] = hmac.new(
                secret.encode(), unsigned.encode(), hashlib.sha256
            ).hexdigest()
            headers["X-OURBIT-APIKEY"] = key
        query = self._query(params)
        url = self.base_url + path + (("?" + query) if query else "")
        return self.transport.request(method, url, headers=headers, timeout=10)
