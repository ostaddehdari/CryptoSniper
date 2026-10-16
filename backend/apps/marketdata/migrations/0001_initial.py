import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("exchanges", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Watchlist",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                            serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                            related_name="market_watchlists",
                                            to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("created_at", "pk")},
        ),
        migrations.CreateModel(
            name="WatchlistItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                            serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("market", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                             related_name="watchlist_items",
                                             to="exchanges.exchangemarket")),
                ("watchlist", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                related_name="items",
                                                to="marketdata.watchlist")),
            ],
            options={"ordering": ("created_at", "pk")},
        ),
        migrations.AddConstraint(
            model_name="watchlist",
            constraint=models.UniqueConstraint(fields=("owner", "name"),
                                               name="market_watchlist_owner_name_unique"),
        ),
        migrations.AddConstraint(
            model_name="watchlistitem",
            constraint=models.UniqueConstraint(fields=("watchlist", "market"),
                                               name="market_watchlist_item_unique"),
        ),
    ]
