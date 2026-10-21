from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("exchanges", "0006_livespotorder")]

    operations = [
        migrations.AddField(
            model_name="userexchangeaccount",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="ExchangeConnectionLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stage", models.CharField(max_length=32)),
                ("status", models.CharField(choices=[("running", "در حال بررسی"), ("success", "موفق"), ("failed", "ناموفق")], max_length=12)),
                ("code", models.CharField(blank=True, max_length=80)),
                ("message", models.CharField(blank=True, max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="connection_logs", to="exchanges.userexchangeaccount")),
            ],
            options={"ordering": ("-created_at", "-pk")},
        ),
        migrations.AddIndex(
            model_name="exchangeconnectionlog",
            index=models.Index(fields=["account", "created_at"], name="exchanges_e_account_16ca1e_idx"),
        ),
    ]
