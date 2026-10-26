from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exchanges", "0007_stage24_liveorder_archived_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="userexchangeaccount",
            name="last_error_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userexchangeaccount",
            name="last_error_code",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="userexchangeaccount",
            name="last_error_message",
            field=models.CharField(blank=True, max_length=240),
        ),
    ]
