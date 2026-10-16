from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import pytest
from apps.exchanges.adapters import UnsafePermissionError, UnsupportedOperationError, get_adapter
from apps.exchanges.binance import BinanceAdapter, safe_request_path


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def request(self, method, url, headers=None, timeout=10):
        self.calls.append((method, url, headers or {}, timeout))
        return self.responses[safe_request_path(url)]


def adapter_with(responses):
    return BinanceAdapter(
        credentials={"api_key": "visible-key", "api_secret": "never-log-secret"},
        transport=FakeTransport(responses),
        clock=lambda: 1700000000000,
    )


def test_permission_probe_requires_no_withdrawal_and_signs_without_exposing_secret():
    adapter = adapter_with(
        {
            "/sapi/v1/account/apiRestrictions": {
                "enableReading": True,
                "enableWithdrawals": False,
                "enableSpotAndMarginTrading": True,
                "enableMargin": True,
                "ipRestrict": True,
                "createTime": 123,
            }
        }
    )
    report = adapter.validate_credentials()
    assert report.safe_for_trading
    _, url, headers, _ = adapter.transport.calls[0]
    query = parse_qs(urlsplit(url).query)
    assert query["timestamp"] == ["1700000000000"]
    assert len(query["signature"][0]) == 64
    assert "never-log-secret" not in url
    assert headers["X-MBX-APIKEY"] == "visible-key"


def test_withdrawal_permission_is_rejected():
    adapter = adapter_with(
        {
            "/sapi/v1/account/apiRestrictions": {
                "enableReading": True,
                "enableWithdrawals": True,
                "enableSpotAndMarginTrading": True,
            }
        }
    )
    with pytest.raises(UnsafePermissionError):
        adapter.validate_credentials()


def test_public_market_and_private_balance_are_normalized():
    adapter = adapter_with(
        {
            "/api/v3/account": {
                "balances": [
                    {"asset": "USDT", "free": "100.25", "locked": "3.75"},
                    {"asset": "ZERO", "free": "0", "locked": "0"},
                ]
            },
            "/api/v3/exchangeInfo": {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "status": "TRADING",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                        "isSpotTradingAllowed": True,
                        "isMarginTradingAllowed": True,
                        "filters": [
                            {
                                "filterType": "LOT_SIZE",
                                "minQty": "0.00001000",
                                "maxQty": "9000",
                                "stepSize": "0.00001000",
                            },
                            {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                            {"filterType": "MIN_NOTIONAL", "minNotional": "10"},
                        ],
                    }
                ]
            },
            "/api/v3/ticker/price": {"symbol": "BTCUSDT", "price": "65000.10"},
        }
    )
    assert adapter.fetch_balance()[0].total == Decimal("104.00")
    markets = adapter.fetch_markets()
    assert [(market.symbol, market.market_type) for market in markets] == [
        ("BTC/USDT", "spot"),
        ("BTC/USDT", "margin"),
    ]
    assert markets[0].min_notional == Decimal("10")
    assert adapter.fetch_ticker("BTC/USDT").price == Decimal("65000.10")


def test_real_order_writes_are_disabled_in_stage_three():
    adapter = get_adapter("binance", credentials={"api_key": "key", "api_secret": "secret"})
    with pytest.raises(UnsupportedOperationError):
        adapter.place_order(symbol="BTC/USDT")
