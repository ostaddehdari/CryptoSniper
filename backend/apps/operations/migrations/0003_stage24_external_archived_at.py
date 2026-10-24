from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operations", "0002_externaltradepolicy")]

    operations = [
        migrations.AddField(
            model_name="externalobservation",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
