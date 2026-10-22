from decimal import Decimal

from apps.exchanges.bitunix import BitunixAdapter
from apps.exchanges.nobitex import NobitexAdapter


class Transport:
    def __init__(self, payloads):
        self.payloads = list(payloads)

    def request(self, *args, **kwargs):
        return self.payloads.pop(0)


def test_bitunix_pending_list_accepts_top_level_data_list():
    adapter = BitunixAdapter(
        credentials={"api_key": "key", "api_secret": "secret"},
        environment="live",
        transport=Transport(
            [
                {
                    "code": 0,
                    "data": [
                        {
                            "orderId": "1",
                            "symbol": "BTCUSDT",
                            "side": "2",
                            "type": "1",
                            "volume": "0.001",
                            "dealVolume": "0",
                            "price": "80000",
                            "status": "1",
                        }
                    ],
                }
            ]
        ),
        clock=lambda: 1724285700000,
    )
    rows = adapter.fetch_open_orders("BTC/USDT")
    assert len(rows) == 1
    assert rows[0].symbol == "BTC/USDT"
    assert rows[0].order_id == "1"


def test_bitunix_history_accepts_nested_page_data():
    adapter = BitunixAdapter(
        credentials={"api_key": "key", "api_secret": "secret"},
        environment="live",
        transport=Transport(
            [
                {
                    "code": 0,
                    "data": {
                        "total": 1,
                        "pageNum": "1",
                        "pageSize": 100,
                        "data": [{"orderId": "7", "symbol": "BTCUSDT"}],
                    },
                }
            ]
        ),
        clock=lambda: 1724285700000,
    )
    rows = adapter.fetch_trade_history("BTC/USDT")
    assert rows == [{"orderId": "7", "symbol": "BTCUSDT"}]


def test_nobitex_ticker_uses_midpoint_when_last_trade_missing():
    adapter = NobitexAdapter(
        credentials={},
        environment="live",
        transport=Transport(
            [
                {
                    "status": "ok",
                    "lastUpdate": 1726651067347,
                    "bids": [["99900", "1"]],
                    "asks": [["100100", "1"]],
                }
            ]
        ),
    )
    ticker = adapter.fetch_ticker("USDT/IRT")
    assert ticker.price == Decimal("100000")
