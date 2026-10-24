from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("signals", "0009_telegramchannel_automation")]

    operations = [
        migrations.AddField(
            model_name="signal",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
