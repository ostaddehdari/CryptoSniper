from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("exchanges", "0008_environment_default_live"),
        ("operations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExternalTradeManagement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=16, max_digits=32)),
                ("entry_price", models.DecimalField(decimal_places=16, max_digits=32)),
                ("stop_loss", models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True)),
                ("tp1", models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True)),
                ("tp2", models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True)),
                ("tp3", models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True)),
                ("trailing_enabled", models.BooleanField(default=False)),
                ("trailing_sl_enabled", models.BooleanField(default=False)),
                ("trailing_trigger", models.CharField(choices=[("tp1", "TP1"), ("tp2", "TP2"), ("tp3", "TP3")], default="tp1", max_length=8)),
                ("trailing_distance_percent", models.DecimalField(decimal_places=4, default=1, max_digits=8)),
                ("high_water", models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True)),
                ("effective_stop", models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True)),
                ("breakeven_moved", models.BooleanField(default=False)),
                ("last_price", models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True)),
                ("last_tick_at", models.DateTimeField(blank=True, null=True)),
                ("state", models.CharField(choices=[("active", "فعال"), ("paused", "متوقف"), ("exiting", "در حال خروج"), ("closed", "بسته"), ("error", "خطا")], default="active", max_length=12)),
                ("last_error", models.CharField(blank=True, max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="exchanges.userexchangeaccount")),
                ("exit_order", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="external_management", to="exchanges.livespotorder")),
                ("market", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="exchanges.exchangemarket")),
                ("observation", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="management", to="operations.externalobservation")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="accounts.user")),
            ],
            options={"ordering": ("-updated_at", "-pk")},
        ),
        migrations.AddConstraint(
            model_name="externaltrademanagement",
            constraint=models.CheckConstraint(condition=models.Q(("quantity__gt", 0)), name="external_management_quantity_positive"),
        ),
        migrations.AddConstraint(
            model_name="externaltrademanagement",
            constraint=models.CheckConstraint(condition=models.Q(("entry_price__gt", 0)), name="external_management_entry_positive"),
        ),
        migrations.AddConstraint(
            model_name="externaltrademanagement",
            constraint=models.CheckConstraint(condition=models.Q(("trailing_distance_percent__gt", 0), ("trailing_distance_percent__lt", 100)), name="external_management_trailing_distance_range"),
        ),
    ]
