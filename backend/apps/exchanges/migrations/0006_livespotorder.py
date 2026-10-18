import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("exchanges", "0005_stage21_multi_exchange_catalog"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="LiveSpotOrder",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("request_key", models.UUIDField(default=uuid.uuid4)),
                ("client_order_id", models.CharField(max_length=80)),
                ("external_order_id", models.CharField(blank=True, max_length=120)),
                (
                    "side",
                    models.CharField(choices=[("buy", "خرید"), ("sell", "فروش")], max_length=4),
                ),
                (
                    "order_type",
                    models.CharField(
                        choices=[("limit", "Limit"), ("market", "Market")], max_length=8
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=16, max_digits=32)),
                (
                    "price",
                    models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True),
                ),
                ("filled_amount", models.DecimalField(decimal_places=16, default=0, max_digits=32)),
                (
                    "average_price",
                    models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True),
                ),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("pending", "در صف"),
                            ("submitting", "در حال ارسال"),
                            ("open", "باز"),
                            ("partial", "بخشی اجرا شده"),
                            ("filled", "تکمیل‌شده"),
                            ("cancelled", "لغوشده"),
                            ("uncertain", "نتیجه نامعلوم"),
                            ("failed", "ناموفق"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("error_code", models.CharField(blank=True, max_length=50)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
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
                        on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddConstraint(
            model_name="livespotorder",
            constraint=models.UniqueConstraint(
                fields=("owner", "request_key"), name="live_spot_order_owner_request_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="livespotorder",
            constraint=models.UniqueConstraint(
                fields=("account", "client_order_id"), name="live_spot_order_account_client_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="livespotorder",
            constraint=models.CheckConstraint(
                condition=Q(("amount__gt", 0)), name="live_spot_order_amount_positive"
            ),
        ),
        migrations.AddConstraint(
            model_name="livespotorder",
            constraint=models.CheckConstraint(
                condition=Q(("price__isnull", True), ("price__gt", 0), _connector="OR"),
                name="live_spot_order_price_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="livespotorder",
            constraint=models.CheckConstraint(
                condition=Q(("filled_amount__gte", 0)), name="live_spot_order_filled_nonnegative"
            ),
        ),
    ]
