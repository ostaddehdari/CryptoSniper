from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("exchanges", "0006_livespotorder")]

    operations = [
        migrations.AddField(
            model_name="livespotorder",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
