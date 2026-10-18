import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("signals", "0006_stage22_channel_templates"),
    ]

    operations = [
        migrations.CreateModel(
            name="SignalOutcome",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "منتظر داده"),
                            ("no_data", "بدون داده"),
                            ("not_triggered", "ورود فعال نشد"),
                            ("open", "فعال"),
                            ("target", "هدف محقق شد"),
                            ("stopped", "حد ضرر"),
                            ("ambiguous", "مبهم"),
                            ("expired", "منقضی"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("provider", models.CharField(default="binance_public", max_length=32)),
                ("symbol", models.CharField(max_length=32)),
                ("interval", models.CharField(default="1h", max_length=8)),
                ("entry_hit_at", models.DateTimeField(blank=True, null=True)),
                ("stop_hit_at", models.DateTimeField(blank=True, null=True)),
                ("targets_hit", models.PositiveSmallIntegerField(default=0)),
                (
                    "last_target_price",
                    models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True),
                ),
                ("evaluated_from", models.DateTimeField()),
                ("evaluated_until", models.DateTimeField(blank=True, null=True)),
                ("policy_version", models.CharField(default="ohlc-conservative-v1", max_length=32)),
                ("evidence", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
                    ),
                ),
                (
                    "signal",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="outcome",
                        to="signals.signal",
                    ),
                ),
            ],
            options={
                "ordering": ("-evaluated_from",),
                "indexes": [
                    models.Index(
                        fields=["owner", "status", "evaluated_from"],
                        name="signals_sig_owner_i_132207_idx",
                    )
                ],
            },
        ),
    ]
