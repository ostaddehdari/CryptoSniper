import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def copy_live_cursor(apps, schema_editor):
    TelegramChannel = apps.get_model("signals", "TelegramChannel")
    for channel in TelegramChannel.objects.all().iterator():
        channel.live_message_id = channel.last_message_id
        channel.save(update_fields=("live_message_id",))


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("signals", "0004_stage22_telegram_verification"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramchannel",
            name="live_message_id",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="telegrammessage",
            name="occurred_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(copy_live_cursor, migrations.RunPython.noop),
        migrations.CreateModel(
            name="TelegramBackfillJob",
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
                            ("running", "در حال دریافت"),
                            ("paused", "متوقف"),
                            ("completed", "کامل"),
                            ("failed", "ناموفق"),
                        ],
                        default="pending",
                        max_length=12,
                    ),
                ),
                ("upper_message_id", models.BigIntegerField(default=0)),
                ("cursor_message_id", models.BigIntegerField(default=0)),
                ("scanned_messages", models.PositiveBigIntegerField(default=0)),
                ("imported_messages", models.PositiveBigIntegerField(default=0)),
                ("skipped_messages", models.PositiveBigIntegerField(default=0)),
                ("batch_size", models.PositiveSmallIntegerField(default=100)),
                ("last_error", models.CharField(blank=True, max_length=80)),
                ("retry_at", models.DateTimeField(blank=True, null=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "channel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="backfill_jobs",
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
            options={
                "ordering": ("-created_at",),
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("batch_size__gte", 20), ("batch_size__lte", 500)),
                        name="telegram_backfill_batch_range",
                    )
                ],
            },
        ),
    ]
