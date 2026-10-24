from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("exchanges", "0004_alter_exchange_website")]

    operations = [
        migrations.AddField(
            model_name="livespotorder",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
