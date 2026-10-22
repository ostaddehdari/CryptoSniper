from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("signals", "0008_telegramevaluationjob"),
    ]

    operations = [
        migrations.AlterField(
            model_name="telegramchannel",
            name="automation",
            field=models.CharField(
                choices=[
                    ("manual", "دستی"),
                    ("semi_auto", "نیمه‌خودکار"),
                    ("full_auto", "Legacy Full-Auto (غیرفعال)"),
                ],
                default="manual",
                max_length=12,
            ),
        ),
    ]
