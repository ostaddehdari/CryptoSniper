import uuid
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("exchanges", "0006_livespotorder"),
        ("operations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExternalTradePolicy",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("entry_price", models.DecimalField(decimal_places=16, max_digits=32)),
                ("remaining_amount", models.DecimalField(decimal_places=16, max_digits=32)),
                ("stop_loss", models.DecimalField(decimal_places=16, max_digits=32)),
                ("tp1", models.DecimalField(decimal_places=16, max_digits=32)),
                (
                    "tp2",
                    models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True),
                ),
                (
                    "tp3",
                    models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True),
                ),
                ("trailing_enabled", models.BooleanField(default=True)),
                ("trailing_sl_enabled", models.BooleanField(default=True)),
                ("trailing_trigger", models.PositiveSmallIntegerField(default=1)),
                (
                    "trailing_distance_percent",
                    models.DecimalField(decimal_places=2, default=Decimal("1"), max_digits=6),
                ),
                ("effective_stop", models.DecimalField(decimal_places=16, max_digits=32)),
                ("trailing_active", models.BooleanField(default=False)),
                (
                    "high_water",
                    models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True),
                ),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("active", "فعال"),
                            ("exit_submitted", "خروج ارسال شده"),
                            ("disabled", "غیرفعال"),
                            ("error", "خطا"),
                        ],
                        default="active",
                        max_length=20,
                    ),
                ),
                (
                    "exit_request_key",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("version", models.PositiveIntegerField(default=1)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "exit_order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="exchanges.livespotorder",
                    ),
                ),
                (
                    "market",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, to="exchanges.exchangemarket"
                    ),
                ),
                (
                    "observation",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="management_policy",
                        to="operations.externalobservation",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="externaltradepolicy",
            constraint=models.CheckConstraint(
                condition=Q(entry_price__gt=0)
                & Q(remaining_amount__gt=0)
                & Q(stop_loss__gt=0)
                & Q(tp1__gt=0),
                name="external_policy_positive_core_values",
            ),
        ),
        migrations.AddConstraint(
            model_name="externaltradepolicy",
            constraint=models.CheckConstraint(
                condition=Q(trailing_trigger__gte=1) & Q(trailing_trigger__lte=3),
                name="external_policy_trigger_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="externaltradepolicy",
            constraint=models.CheckConstraint(
                condition=Q(trailing_distance_percent__gt=0) & Q(trailing_distance_percent__lt=100),
                name="external_policy_distance_range",
            ),
        ),
    ]
