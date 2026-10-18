from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("signals", "0003_alter_signalsource_method")]

    operations = [
        migrations.AddField(
            model_name="telegramaccount",
            name="verification_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="telegramaccount",
            name="verification_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="telegramaccount",
            name="verification_resend_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="telegramaccount",
            name="verification_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
