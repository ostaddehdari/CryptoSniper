from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("marketdata", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="HistoricalCandle",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("provider", models.CharField(max_length=32)),
                ("symbol", models.CharField(max_length=32)),
                ("interval", models.CharField(default="1h", max_length=8)),
                ("open_time", models.DateTimeField()),
                ("close_time", models.DateTimeField()),
                ("open_price", models.DecimalField(decimal_places=16, max_digits=32)),
                ("high_price", models.DecimalField(decimal_places=16, max_digits=32)),
                ("low_price", models.DecimalField(decimal_places=16, max_digits=32)),
                ("close_price", models.DecimalField(decimal_places=16, max_digits=32)),
                ("volume", models.DecimalField(decimal_places=16, default=0, max_digits=40)),
                ("fetched_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("open_time",),
                "indexes": [
                    models.Index(
                        fields=["symbol", "interval", "open_time"],
                        name="marketdata__symbol_3c4c8a_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("provider", "symbol", "interval", "open_time"),
                        name="historical_candle_provider_symbol_time_unique",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("high_price__gte", models.F("low_price")),
                            ("open_price__gte", models.F("low_price")),
                            ("open_price__lte", models.F("high_price")),
                            ("close_price__gte", models.F("low_price")),
                            ("close_price__lte", models.F("high_price")),
                        ),
                        name="historical_candle_valid_ohlc",
                    ),
                ],
            },
        ),
    ]
