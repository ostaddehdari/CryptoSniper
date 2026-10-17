import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="PerformanceAggregate",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("timezone", models.CharField(max_length=64)),
                (
                    "period_kind",
                    models.CharField(
                        choices=[("day", "روز"), ("week", "هفته"), ("month", "ماه")], max_length=8
                    ),
                ),
                ("period_start", models.DateField()),
                (
                    "dimension_kind",
                    models.CharField(
                        choices=[
                            ("total", "همه"),
                            ("coin", "ارز"),
                            ("exchange", "صرافی"),
                            ("source", "منبع"),
                        ],
                        max_length=12,
                    ),
                ),
                ("dimension_value", models.CharField(max_length=80)),
                ("mode", models.CharField(max_length=12)),
                ("currency", models.CharField(max_length=20)),
                ("trade_count", models.PositiveIntegerField(default=0)),
                ("unknown_count", models.PositiveIntegerField(default=0)),
                ("wins", models.PositiveIntegerField(default=0)),
                ("losses", models.PositiveIntegerField(default=0)),
                ("breakeven", models.PositiveIntegerField(default=0)),
                (
                    "gross_realized",
                    models.DecimalField(decimal_places=16, default=0, max_digits=40),
                ),
                ("net_realized", models.DecimalField(decimal_places=16, default=0, max_digits=40)),
                ("fees", models.DecimalField(decimal_places=16, default=0, max_digits=40)),
                (
                    "margin_interest",
                    models.DecimalField(decimal_places=16, default=0, max_digits=40),
                ),
                ("duration_seconds", models.PositiveBigIntegerField(default=0)),
                ("source_fingerprint", models.CharField(max_length=64)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="performance_aggregates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("period_start", "dimension_kind", "dimension_value")},
        ),
        migrations.AddConstraint(
            model_name="performanceaggregate",
            constraint=models.UniqueConstraint(
                fields=(
                    "owner",
                    "timezone",
                    "period_kind",
                    "period_start",
                    "dimension_kind",
                    "dimension_value",
                    "mode",
                    "currency",
                ),
                name="report_aggregate_identity_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="performanceaggregate",
            index=models.Index(
                fields=["owner", "period_kind", "period_start"],
                name="reports_per_owner_i_f2f314_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="performanceaggregate",
            index=models.Index(
                fields=["owner", "dimension_kind", "dimension_value"],
                name="reports_per_owner_i_786a12_idx",
            ),
        ),
    ]
