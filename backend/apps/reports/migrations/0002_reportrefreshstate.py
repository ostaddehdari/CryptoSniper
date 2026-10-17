import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("reports", "0001_initial"),
    ]
    operations = [
        migrations.CreateModel(
            name="ReportRefreshState",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("source_version", models.PositiveBigIntegerField(default=1)),
                ("built_version", models.PositiveBigIntegerField(default=0)),
                ("dirty_at", models.DateTimeField(blank=True, null=True)),
                ("last_built_at", models.DateTimeField(blank=True, null=True)),
                (
                    "owner",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="report_refresh",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        )
    ]
