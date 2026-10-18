import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("signals", "0007_signaloutcome"),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramEvaluationJob",
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
                            ("pending", "در صف"),
                            ("running", "در حال ارزیابی"),
                            ("completed", "کامل"),
                            ("failed", "ناموفق"),
                        ],
                        default="pending",
                        max_length=12,
                    ),
                ),
                ("cursor_signal_id", models.BigIntegerField(default=0)),
                ("total_signals", models.PositiveBigIntegerField(default=0)),
                ("evaluated_signals", models.PositiveBigIntegerField(default=0)),
                ("skipped_signals", models.PositiveBigIntegerField(default=0)),
                ("last_error", models.CharField(blank=True, max_length=80)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "channel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="evaluation_jobs",
                        to="signals.telegramchannel",
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
    ]
