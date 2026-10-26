import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exchanges", "0008_react_connection_diagnostics"),
        ("tradeplans", "0003_stage23_trailing_trigger"),
    ]
    operations = [
        migrations.AddField(
            model_name="livespotorder",
            name="source_plan",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="live_entry_orders",
                to="tradeplans.tradeplan",
            ),
        ),
    ]
