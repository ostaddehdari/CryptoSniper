import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("signals", "0005_stage22_telegram_archive"),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramChannelTemplate",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=80)),
                ("version", models.PositiveIntegerField(default=1)),
                ("priority", models.PositiveSmallIntegerField(default=100)),
                (
                    "message_kind",
                    models.CharField(
                        choices=[
                            ("signal", "سیگنال"),
                            ("update", "به‌روزرسانی"),
                            ("cancel", "لغو"),
                            ("result", "نتیجه"),
                            ("noise", "غیرسیگنال"),
                        ],
                        default="signal",
                        max_length=12,
                    ),
                ),
                ("definition", models.JSONField(default=dict)),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "channel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="templates",
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
                "ordering": ("priority", "pk"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("channel", "name", "version"),
                        name="telegram_template_channel_name_version_unique",
                    )
                ],
            },
        ),
        migrations.AddField(
            model_name="telegrammessage",
            name="matched_template",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="messages",
                to="signals.telegramchanneltemplate",
            ),
        ),
        migrations.AddField(
            model_name="telegrammessage",
            name="message_kind",
            field=models.CharField(
                choices=[
                    ("signal", "سیگنال"),
                    ("update", "به‌روزرسانی"),
                    ("cancel", "لغو"),
                    ("result", "نتیجه"),
                    ("noise", "غیرسیگنال"),
                ],
                default="signal",
                max_length=12,
            ),
        ),
    ]
