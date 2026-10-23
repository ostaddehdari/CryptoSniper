from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("trading", "0006_papermarginloan")]

    operations = [
        migrations.AddField(
            model_name="tradeprotection",
            name="trigger_target",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddConstraint(
            model_name="tradeprotection",
            constraint=models.CheckConstraint(
                condition=Q(trigger_target__gte=1) & Q(trigger_target__lte=3),
                name="paper_trailing_trigger_target_valid",
            ),
        ),
    ]
