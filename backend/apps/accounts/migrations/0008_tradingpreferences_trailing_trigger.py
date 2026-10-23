from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_wallet_index_name")]

    operations = [
        migrations.AlterField(
            model_name="tradingpreferences",
            name="trailing_trigger",
            field=models.CharField(
                choices=[
                    ("tp1", "پس از TP1"),
                    ("tp2", "پس از TP2"),
                    ("tp3", "پس از TP3"),
                ],
                default="tp1",
                max_length=8,
                verbose_name="شروع Trailing",
            ),
        ),
    ]
