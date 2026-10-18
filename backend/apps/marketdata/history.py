"""Public historical-candle acquisition with strict normalization and bounded pages."""

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.core.exceptions import ValidationError

from .models import HistoricalCandle

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
INTERVAL_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


class PublicJsonTransport:
    def request(self, method, url, timeout=15):
        request = Request(
            url,
            method=method,
            headers={"Accept": "application/json", "User-Agent": "CryptoSniper/0.22"},
        )
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ValidationError("دریافت تاریخچه عمومی بازار ناموفق بود.") from error


def _decimal(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValidationError("داده کندل عدد معتبر ندارد.") from error
    if not number.is_finite() or number < 0:
        raise ValidationError("داده کندل عدد معتبر ندارد.")
    return number


def fetch_binance_history(symbol, start, end, *, interval="1h", transport=None, max_pages=20):
    if interval not in INTERVAL_MS or start >= end:
        raise ValidationError("بازه یا interval تاریخچه معتبر نیست.")
    transport = transport or PublicJsonTransport()
    provider_symbol = symbol.replace("/", "").upper()
    cursor = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    rows = []
    for _ in range(max_pages):
        query = urlencode(
            {
                "symbol": provider_symbol,
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1000,
            }
        )
        payload = transport.request("GET", BINANCE_KLINES + "?" + query, timeout=15)
        if not isinstance(payload, list):
            raise ValidationError("پاسخ تاریخچه بازار معتبر نیست.")
        if not payload:
            break
        for item in payload:
            if not isinstance(item, list) or len(item) < 7:
                raise ValidationError("ساختار کندل بازار معتبر نیست.")
            rows.append(
                HistoricalCandle(
                    provider="binance_public",
                    symbol=symbol.upper(),
                    interval=interval,
                    open_time=datetime.fromtimestamp(int(item[0]) / 1000, tz=UTC),
                    close_time=datetime.fromtimestamp(int(item[6]) / 1000, tz=UTC),
                    open_price=_decimal(item[1]),
                    high_price=_decimal(item[2]),
                    low_price=_decimal(item[3]),
                    close_price=_decimal(item[4]),
                    volume=_decimal(item[5]),
                )
            )
        next_cursor = int(payload[-1][0]) + INTERVAL_MS[interval]
        if next_cursor <= cursor or next_cursor > end_ms or len(payload) < 1000:
            break
        cursor = next_cursor
    HistoricalCandle.objects.bulk_create(
        rows,
        update_conflicts=True,
        update_fields=(
            "close_time",
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "volume",
        ),
        unique_fields=("provider", "symbol", "interval", "open_time"),
    )
    return len(rows)
