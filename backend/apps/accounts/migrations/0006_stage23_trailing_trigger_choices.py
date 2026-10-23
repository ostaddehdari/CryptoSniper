from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_auditlog")]

    operations = [
        migrations.AlterField(
            model_name="tradingpreferences",
            name="trailing_tp_enabled",
            field=models.BooleanField(default=True, verbose_name="Trailing"),
        ),
        migrations.AlterField(
            model_name="tradingpreferences",
            name="trailing_trigger",
            field=models.CharField(
                choices=[("tp1", "TP1"), ("tp2", "TP2"), ("tp3", "TP3")],
                default="tp1",
                max_length=8,
                verbose_name="شروع Trailing",
            ),
        ),
    ]
