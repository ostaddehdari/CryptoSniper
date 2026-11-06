from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tradeplans", "0003_stage23_trailing_trigger")]

    operations = [
        migrations.AddField(
            model_name="tradeplan",
            name="order_type",
            field=models.CharField(
                choices=[("limit", "Limit"), ("market", "Market")],
                default="limit",
                max_length=8,
            ),
        )
    ]
