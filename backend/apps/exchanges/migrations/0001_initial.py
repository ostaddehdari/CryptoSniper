import decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_exchange_catalog(apps, schema_editor):
    Exchange = apps.get_model("exchanges", "Exchange")
    Exchange.objects.update_or_create(
        code="simulator",
        defaults={
            "name": "شبیه‌ساز CryptoSniper",
            "adapter_code": "simulator",
            "spot_supported": True,
            "margin_supported": True,
            "futures_supported": False,
            "sandbox_supported": True,
            "enabled": True,
        },
    )
    Exchange.objects.update_or_create(
        code="binance",
        defaults={
            "name": "Binance",
            "website": "https://www.binance.com/",
            "adapter_code": "binance",
            "spot_supported": True,
            "margin_supported": True,
            "futures_supported": False,
            "sandbox_supported": False,
            "enabled": True,
        },
    )


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("accounts", "0005_auditlog"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="Asset",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "symbol",
                    models.CharField(
                        max_length=20,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                "^[A-Z0-9]{2,20}$", "نماد باید فقط شامل حروف بزرگ لاتین و عدد باشد."
                            )
                        ],
                    ),
                ),
                ("name", models.CharField(blank=True, max_length=80)),
                ("active", models.BooleanField(default=True)),
            ],
            options={"ordering": ("symbol",)},
        ),
        migrations.CreateModel(
            name="Exchange",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("code", models.SlugField(max_length=32, unique=True)),
                ("name", models.CharField(max_length=80)),
                ("website", models.URLField(blank=True)),
                ("adapter_code", models.SlugField(max_length=32, unique=True)),
                ("spot_supported", models.BooleanField(default=True)),
                ("margin_supported", models.BooleanField(default=False)),
                ("futures_supported", models.BooleanField(default=False)),
                ("sandbox_supported", models.BooleanField(default=False)),
                ("enabled", models.BooleanField(default=True)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="UserExchangeAccount",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("label", models.CharField(max_length=80)),
                (
                    "environment",
                    models.CharField(
                        choices=[
                            ("paper", "شبیه‌ساز"),
                            ("sandbox", "آزمایشی صرافی"),
                            ("live", "حساب اصلی"),
                        ],
                        default="paper",
                        max_length=12,
                    ),
                ),
                ("credentials_encrypted", models.TextField(blank=True, editable=False)),
                ("credential_hint", models.CharField(blank=True, editable=False, max_length=24)),
                (
                    "credential_key_version",
                    models.PositiveSmallIntegerField(default=1, editable=False),
                ),
                ("trading_enabled", models.BooleanField(default=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "در انتظار بررسی"),
                            ("connected", "متصل"),
                            ("restricted", "محدود"),
                            ("error", "خطا"),
                            ("disabled", "غیرفعال"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("permissions", models.JSONField(blank=True, default=dict)),
                ("last_verified_at", models.DateTimeField(blank=True, null=True)),
                ("last_sync_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "exchange",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="accounts",
                        to="exchanges.exchange",
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
        migrations.CreateModel(
            name="ExchangeMarket",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("symbol", models.CharField(max_length=48)),
                (
                    "market_type",
                    models.CharField(
                        choices=[("spot", "Spot"), ("margin", "Margin")], max_length=12
                    ),
                ),
                (
                    "min_amount",
                    models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True),
                ),
                (
                    "max_amount",
                    models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True),
                ),
                (
                    "amount_step",
                    models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True),
                ),
                (
                    "price_step",
                    models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True),
                ),
                (
                    "min_notional",
                    models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True),
                ),
                (
                    "max_leverage",
                    models.DecimalField(
                        decimal_places=4,
                        default=decimal.Decimal("1"),
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(decimal.Decimal("1"))],
                    ),
                ),
                (
                    "maker_fee",
                    models.DecimalField(blank=True, decimal_places=8, max_digits=12, null=True),
                ),
                (
                    "taker_fee",
                    models.DecimalField(blank=True, decimal_places=8, max_digits=12, null=True),
                ),
                ("active", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("synced_at", models.DateTimeField(blank=True, null=True)),
                (
                    "base_asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="base_markets",
                        to="exchanges.asset",
                    ),
                ),
                (
                    "exchange",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="markets",
                        to="exchanges.exchange",
                    ),
                ),
                (
                    "quote_asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="quote_markets",
                        to="exchanges.asset",
                    ),
                ),
            ],
            options={"ordering": ("exchange__name", "symbol", "market_type")},
        ),
        migrations.CreateModel(
            name="BalanceSnapshot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("free_balance", models.DecimalField(decimal_places=16, default=0, max_digits=32)),
                (
                    "locked_balance",
                    models.DecimalField(decimal_places=16, default=0, max_digits=32),
                ),
                ("total_balance", models.DecimalField(decimal_places=16, default=0, max_digits=32)),
                (
                    "usd_value",
                    models.DecimalField(blank=True, decimal_places=8, max_digits=32, null=True),
                ),
                ("captured_at", models.DateTimeField()),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="balance_snapshots",
                        to="exchanges.asset",
                    ),
                ),
                (
                    "exchange_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="balance_snapshots",
                        to="exchanges.userexchangeaccount",
                    ),
                ),
            ],
            options={"ordering": ("-captured_at", "asset__symbol")},
        ),
        migrations.AddConstraint(
            model_name="userexchangeaccount",
            constraint=models.UniqueConstraint(
                fields=("owner", "exchange", "label"), name="user_exchange_account_label_unique"
            ),
        ),
        migrations.AddIndex(
            model_name="userexchangeaccount",
            index=models.Index(
                fields=["owner", "status", "exchange"], name="exchanges_u_owner_i_7d3603_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="exchangemarket",
            constraint=models.UniqueConstraint(
                fields=("exchange", "symbol", "market_type"),
                name="exchange_market_symbol_type_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="exchangemarket",
            constraint=models.CheckConstraint(
                condition=models.Q(("market_type__in", ("spot", "margin"))),
                name="exchange_market_v1_type_supported",
            ),
        ),
        migrations.AddConstraint(
            model_name="exchangemarket",
            constraint=models.CheckConstraint(
                condition=models.Q(("max_leverage__gte", 1)),
                name="exchange_market_leverage_at_least_one",
            ),
        ),
        migrations.AddIndex(
            model_name="exchangemarket",
            index=models.Index(
                fields=["exchange", "symbol", "market_type", "active"],
                name="exchanges_e_exchang_96f8de_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="balancesnapshot",
            constraint=models.UniqueConstraint(
                fields=("exchange_account", "asset", "captured_at"),
                name="balance_snapshot_account_asset_time_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="balancesnapshot",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("free_balance__gte", 0), ("locked_balance__gte", 0), ("total_balance__gte", 0)
                ),
                name="balance_snapshot_nonnegative",
            ),
        ),
        migrations.AddIndex(
            model_name="balancesnapshot",
            index=models.Index(
                fields=["exchange_account", "captured_at"], name="exchanges_b_exchang_39ca0d_idx"
            ),
        ),
        migrations.RunPython(seed_exchange_catalog, migrations.RunPython.noop),
    ]
