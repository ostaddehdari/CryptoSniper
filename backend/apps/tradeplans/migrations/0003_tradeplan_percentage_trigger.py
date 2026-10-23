from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tradeplans", "0002_tradeplan_origin_signal")]

    operations = [
        migrations.AddField(
            model_name="tradeplan",
            name="percentage_trigger",
            field=models.CharField(
                choices=[("tp1", "TP1"), ("tp2", "TP2"), ("tp3", "TP3")],
                default="tp1",
                max_length=8,
            ),
        ),
    ]
