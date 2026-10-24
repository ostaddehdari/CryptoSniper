from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("trading", "0007_stage23_trailing_trigger_target")]

    operations = [
        migrations.AddField(
            model_name="trade",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
