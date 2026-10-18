from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from apps.exchanges.adapters import get_adapter
from apps.exchanges.bitunix import BitunixAdapter
from apps.exchanges.lbank import LbankAdapter
from apps.exchanges.nobitex import NobitexAdapter
from apps.exchanges.spot_v3 import OurbitAdapter, WeexAdapter


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def request(self, method, url, headers=None, body=None, timeout=10):
        self.calls.append((method, url, headers or {}, body, timeout))
        return self.responses[urlsplit(url).path]


def test_all_requested_adapters_are_registered():
    assert [
        get_adapter(code).code for code in ("nobitex", "lbank", "weex", "ourbit", "bitunix")
    ] == [
        "nobitex",
        "lbank",
        "weex",
        "ourbit",
        "bitunix",
    ]


def test_weex_permission_signature_and_limit_order_normalization():
    transport = FakeTransport(
        {
            "/api/v3/account": {
                "canTrade": True,
                "canWithdraw": False,
                "permissions": ["SPOT_TRADING"],
                "balances": [],
                "uid": 7,
            },
            "/api/v3/order": {
                "symbol": "BTCUSDT",
                "orderId": 42,
                "clientOrderId": "client-1",
                "transactTime": 1700000000000,
            },
        }
    )
    adapter = WeexAdapter(
        {"api_key": "key", "api_secret": "secret", "passphrase": "phrase"},
        transport=transport,
        clock=lambda: 1700000000000,
    )
    assert adapter.validate_credentials().safe_for_trading
    order = adapter.place_order(
        symbol="BTC/USDT",
        side="buy",
        order_type="limit",
        amount="0.01",
        price="60000",
        client_order_id="client-1",
    )
    assert order.order_id == "42" and order.amount == Decimal("0.01")
    assert transport.calls[0][2]["ACCESS-PASSPHRASE"] == "phrase"
    assert "secret" not in transport.calls[0][1]


def test_ourbit_signs_query_and_rejects_no_fields_from_secret():
    transport = FakeTransport(
        {
            "/api/v3/account": {
                "canTrade": True,
                "canWithdraw": False,
                "permissions": ["SPOT"],
                "balances": [],
            }
        }
    )
    adapter = OurbitAdapter(
        {"api_key": "our-key", "api_secret": "our-secret"},
        transport=transport,
        clock=lambda: 1700000000000,
    )
    assert adapter.validate_credentials().safe_for_trading
    _, url, headers, _, _ = transport.calls[0]
    assert headers["X-OURBIT-APIKEY"] == "our-key"
    assert len(parse_qs(urlsplit(url).query)["signature"][0]) == 64
    assert "our-secret" not in url


def test_nobitex_reads_wallets_and_uses_token_without_secret():
    transport = FakeTransport(
        {
            "/users/wallets/list": {
                "status": "ok",
                "wallets": [
                    {
                        "currency": "usdt",
                        "balance": "20",
                        "blockedBalance": "1",
                        "activeBalance": "19",
                    }
                ],
            }
        }
    )
    adapter = NobitexAdapter(
        {"api_key": "token", "no_withdrawal_confirmed": "true"}, transport=transport
    )
    assert adapter.validate_credentials().safe_for_trading
    assert adapter.fetch_balance()[0].total == Decimal("20")
    assert transport.calls[0][2]["Authorization"] == "Token token"


def test_lbank_hmac_headers_and_account_permissions():
    transport = FakeTransport(
        {
            "/v2/supplement/api_Restrictions.do": {
                "result": True,
                "data": {
                    "enableReading": True,
                    "enableSpotTrading": True,
                    "enableWithdrawals": False,
                    "ipRestrict": True,
                },
            }
        }
    )
    adapter = LbankAdapter(
        {"api_key": "lb-key", "api_secret": "lb-secret"},
        transport=transport,
        clock=lambda: 1700000000000,
    )
    assert adapter.validate_credentials().safe_for_trading
    _, url, headers, body, _ = transport.calls[0]
    assert urlsplit(url).query == ""
    assert headers["signature_method"] == "HmacSHA256"
    fields = parse_qs(body)
    assert {"api_key", "timestamp", "signature_method", "echostr", "sign"} <= fields.keys()
    assert "lb-secret" not in body


def test_bitunix_double_sha_signature_and_manual_no_withdrawal_gate():
    transport = FakeTransport({"/api/spot/v1/user/account": {"code": 0, "data": []}})
    adapter = BitunixAdapter(
        {
            "api_key": "bx-key",
            "api_secret": "bx-secret",
            "no_withdrawal_confirmed": "true",
        },
        transport=transport,
        clock=lambda: 1700000000000,
    )
    assert adapter.validate_credentials().safe_for_trading
    _, url, headers, _, _ = transport.calls[0]
    assert len(headers["sign"]) == 64
    assert "bx-secret" not in url and "bx-secret" not in headers["sign"]
