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
