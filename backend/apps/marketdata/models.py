from django.conf import settings
from django.db import models


class Watchlist(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="market_watchlists"
    )
    name = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "name"), name="market_watchlist_owner_name_unique"
            )
        ]

    def __str__(self):
        return self.name


class WatchlistItem(models.Model):
    watchlist = models.ForeignKey(Watchlist, on_delete=models.CASCADE, related_name="items")
    market = models.ForeignKey(
        "exchanges.ExchangeMarket", on_delete=models.CASCADE, related_name="watchlist_items"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("watchlist", "market"), name="market_watchlist_item_unique"
            )
        ]

    def __str__(self):
        return f"{self.watchlist_id}:{self.market_id}"


class HistoricalCandle(models.Model):
    """Normalized public OHLC data used only for historical evidence."""

    provider = models.CharField(max_length=32)
    symbol = models.CharField(max_length=32)
    interval = models.CharField(max_length=8, default="1h")
    open_time = models.DateTimeField()
    close_time = models.DateTimeField()
    open_price = models.DecimalField(max_digits=32, decimal_places=16)
    high_price = models.DecimalField(max_digits=32, decimal_places=16)
    low_price = models.DecimalField(max_digits=32, decimal_places=16)
    close_price = models.DecimalField(max_digits=32, decimal_places=16)
    volume = models.DecimalField(max_digits=40, decimal_places=16, default=0)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("open_time",)
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "symbol", "interval", "open_time"),
                name="historical_candle_provider_symbol_time_unique",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(high_price__gte=models.F("low_price"))
                    & models.Q(open_price__gte=models.F("low_price"))
                    & models.Q(open_price__lte=models.F("high_price"))
                    & models.Q(close_price__gte=models.F("low_price"))
                    & models.Q(close_price__lte=models.F("high_price"))
                ),
                name="historical_candle_valid_ohlc",
            ),
        ]
        indexes = [models.Index(fields=("symbol", "interval", "open_time"))]

    def __str__(self):
        return f"{self.provider}:{self.symbol}:{self.interval}:{self.open_time.isoformat()}"

class FavoriteAsset(models.Model):
    """User-ordered asset symbols shown first across connected exchanges."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorite_assets",
    )
    symbol = models.CharField(max_length=20)
    position = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("position", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "symbol"),
                name="favorite_asset_owner_symbol_unique",
            )
        ]
        indexes = [models.Index(fields=("owner", "position"))]

    def save(self, *args, **kwargs):
        self.symbol = self.symbol.strip().upper()
        return super().save(*args, **kwargs)

