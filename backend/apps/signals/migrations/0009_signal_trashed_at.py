from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("signals", "0008_telegramevaluationjob")]

    operations = [
        migrations.AddField(
            model_name="signal",
            name="trashed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
