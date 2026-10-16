import decimal
import uuid

import django.core.validators
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
            name="TradePlan",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("client_token", models.UUIDField(default=uuid.uuid4)),
                ("source", models.CharField(default="manual", max_length=24)),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "پیش‌نویس"), ("ready", "تأییدشده برای بررسی")],
                        default="draft",
                        max_length=8,
                    ),
                ),
                (
                    "side",
                    models.CharField(
                        choices=[("long", "خرید / Long"), ("short", "فروش / Short")],
                        default="long",
                        max_length=8,
                    ),
                ),
                ("entry_price", models.DecimalField(max_digits=32, decimal_places=16)),
                ("stop_loss", models.DecimalField(max_digits=32, decimal_places=16)),
                ("tp1", models.DecimalField(max_digits=32, decimal_places=16)),
                (
                    "tp2",
                    models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True),
                ),
                (
                    "tp3",
                    models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True),
                ),
                (
                    "capital",
                    models.DecimalField(
                        max_digits=32,
                        decimal_places=16,
                        validators=[
                            django.core.validators.MinValueValidator(decimal.Decimal("0.00000001"))
                        ],
                    ),
                ),
                (
                    "leverage",
                    models.DecimalField(
                        max_digits=10, decimal_places=4, default=decimal.Decimal("1")
                    ),
                ),
                ("trailing_sl", models.BooleanField(default=False)),
                ("percentage_trailing", models.BooleanField(default=False)),
                (
                    "trailing_distance",
                    models.DecimalField(
                        max_digits=8, decimal_places=4, default=decimal.Decimal("1")
                    ),
                ),
                ("preview", models.JSONField(default=dict)),
                ("approved_snapshot", models.JSONField(default=dict, blank=True)),
                ("revision", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("approved_at", models.DateTimeField(null=True, blank=True)),
                (
                    "exchange_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="exchanges.userexchangeaccount",
                    ),
                ),
                (
                    "market",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, to="exchanges.exchangemarket"
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="trade_plans",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddConstraint(
            model_name="tradeplan",
            constraint=models.UniqueConstraint(
                fields=("owner", "client_token"), name="tradeplan_owner_token_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="tradeplan",
            constraint=models.CheckConstraint(
                condition=models.Q(("capital__gt", 0)), name="tradeplan_capital_positive"
            ),
        ),
        migrations.AddConstraint(
            model_name="tradeplan",
            constraint=models.CheckConstraint(
                condition=models.Q(("leverage__gte", 1)), name="tradeplan_leverage_positive"
            ),
        ),
    ]
