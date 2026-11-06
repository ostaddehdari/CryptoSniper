from django.db import migrations, models
from django.db.models import F, Q


def copy_limit_prices(apps, schema_editor):
    order = apps.get_model("exchanges", "LiveSpotOrder")
    order.objects.filter(reference_price__isnull=True, price__isnull=False).update(
        reference_price=F("price")
    )


class Migration(migrations.Migration):
    dependencies = [("exchanges", "0010_live_order_fee_receipt")]

    operations = [
        migrations.AddField(
            model_name="livespotorder",
            name="reference_price",
            field=models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True),
        ),
        migrations.RunPython(copy_limit_prices, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="livespotorder",
            constraint=models.CheckConstraint(
                condition=Q(reference_price__isnull=True) | Q(reference_price__gt=0),
                name="live_spot_order_reference_price_positive",
            ),
        ),
    ]
