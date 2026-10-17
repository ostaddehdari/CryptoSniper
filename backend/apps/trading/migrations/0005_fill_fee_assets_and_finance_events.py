import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "exchanges",
            "0003_remove_balancesnapshot_balance_snapshot_account_asset_time_unique_and_more",
        ),
        ("trading", "0004_tradeaction"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderfill",
            name="fee_asset",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="entry_fee_fills",
                to="exchanges.asset",
            ),
        ),
        migrations.AddField(
            model_name="orderfill",
            name="fee_quote_rate",
            field=models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True),
        ),
        migrations.AddField(
            model_name="paperexitfill",
            name="fee_asset",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="exit_fee_fills",
                to="exchanges.asset",
            ),
        ),
        migrations.AddField(
            model_name="paperexitfill",
            name="fee_quote_rate",
            field=models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True),
        ),
        migrations.CreateModel(
            name="TradeFinanceEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("borrow_interest", "بهره وام Margin"),
                            ("repayment", "بازپرداخت اصل وام"),
                        ],
                        max_length=24,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=16, max_digits=32)),
                (
                    "quote_rate",
                    models.DecimalField(
                        blank=True,
                        decimal_places=16,
                        help_text="نرخ قطعی دارایی هزینه به ارز quote در زمان رویداد",
                        max_digits=32,
                        null=True,
                    ),
                ),
                ("provider_reference", models.CharField(max_length=120)),
                ("occurred_at", models.DateTimeField()),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, to="exchanges.asset"
                    ),
                ),
                (
                    "trade",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="finance_events",
                        to="trading.trade",
                    ),
                ),
            ],
            options={"ordering": ("occurred_at", "pk")},
        ),
        migrations.AddConstraint(
            model_name="tradefinanceevent",
            constraint=models.UniqueConstraint(
                fields=("trade", "provider_reference"),
                name="trade_finance_provider_reference_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="tradefinanceevent",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount__gt", 0)), name="trade_finance_amount_positive"
            ),
        ),
        migrations.AddConstraint(
            model_name="tradefinanceevent",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("quote_rate__isnull", True), ("quote_rate__gt", 0), _connector="OR"
                ),
                name="trade_finance_quote_rate_positive",
            ),
        ),
    ]
