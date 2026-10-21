from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("exchanges", "0007_connection_diagnostics")]
    operations = [
        migrations.AlterField(
            model_name="userexchangeaccount",
            name="environment",
            field=models.CharField(
                choices=[("paper", "شبیه‌ساز"), ("sandbox", "آزمایشی صرافی"), ("live", "حساب اصلی")],
                default="live",
                max_length=12,
            ),
        ),
    ]
