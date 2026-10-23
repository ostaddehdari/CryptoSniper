from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0002_externaltrademanagement"),
        ("tradeplans", "0003_tradeplan_percentage_trigger"),
        ("exchanges", "0008_environment_default_live"),
    ]

    operations = [
        migrations.CreateModel(
            name="ManagedLiveTrade",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("initial_quantity", models.DecimalField(decimal_places=16, default=0, max_digits=32)),
                ("remaining_quantity", models.DecimalField(decimal_places=16, default=0, max_digits=32)),
                ("entry_price", models.DecimalField(decimal_places=16, max_digits=32)),
                ("initial_stop", models.DecimalField(decimal_places=16, max_digits=32)),
                ("effective_stop", models.DecimalField(decimal_places=16, max_digits=32)),
                ("trailing_enabled", models.BooleanField(default=False)),
                ("trailing_sl_enabled", models.BooleanField(default=False)),
                ("trailing_trigger", models.CharField(choices=[("tp1", "TP1"), ("tp2", "TP2"), ("tp3", "TP3")], default="tp1", max_length=8)),
                ("trailing_distance_percent", models.DecimalField(decimal_places=4, default=1, max_digits=8)),
                ("high_water", models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True)),
                ("breakeven_moved", models.BooleanField(default=False)),
                ("last_price", models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True)),
                ("last_tick_at", models.DateTimeField(blank=True, null=True)),
                ("state", models.CharField(choices=[("pending_entry", "منتظر تکمیل ورود"), ("active", "فعال"), ("paused", "متوقف"), ("exiting", "در حال خروج"), ("closed", "بسته"), ("error", "خطا")], default="pending_entry", max_length=16)),
                ("last_error", models.CharField(blank=True, max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="exchanges.userexchangeaccount")),
                ("entry_order", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="managed_entry", to="exchanges.livespotorder")),
                ("market", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="exchanges.exchangemarket")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="accounts.user")),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="tradeplans.tradeplan")),
            ],
            options={"ordering": ("-updated_at", "-pk")},
        ),
        migrations.CreateModel(
            name="ManagedLiveTarget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveSmallIntegerField()),
                ("price", models.DecimalField(decimal_places=16, max_digits=32)),
                ("share_percent", models.DecimalField(decimal_places=2, max_digits=5)),
                ("allocated_quantity", models.DecimalField(decimal_places=16, default=0, max_digits=32)),
                ("state", models.CharField(choices=[("waiting", "منتظر"), ("exit_pending", "خروج در صف"), ("filled", "تکمیل"), ("skipped", "عبور شد")], default="waiting", max_length=16)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("exit_order", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="managed_target_exit", to="exchanges.livespotorder")),
                ("management", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="targets", to="operations.managedlivetrade")),
            ],
            options={"ordering": ("position",)},
        ),
        migrations.CreateModel(
            name="ManagedLiveExit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason", models.CharField(max_length=24)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("management", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="full_exit", to="operations.managedlivetrade")),
                ("order", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="managed_full_exit", to="exchanges.livespotorder")),
            ],
        ),
        migrations.AddConstraint(
            model_name="managedlivetrade",
            constraint=models.CheckConstraint(condition=models.Q(("entry_price__gt", 0)), name="managed_live_entry_positive"),
        ),
        migrations.AddConstraint(
            model_name="managedlivetrade",
            constraint=models.CheckConstraint(condition=models.Q(("initial_stop__gt", 0)), name="managed_live_stop_positive"),
        ),
        migrations.AddConstraint(
            model_name="managedlivetrade",
            constraint=models.CheckConstraint(condition=models.Q(("initial_quantity__gte", 0), ("remaining_quantity__gte", 0)), name="managed_live_quantity_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="managedlivetrade",
            constraint=models.CheckConstraint(condition=models.Q(("trailing_distance_percent__gt", 0), ("trailing_distance_percent__lt", 100)), name="managed_live_distance_range"),
        ),
        migrations.AddConstraint(
            model_name="managedlivetarget",
            constraint=models.UniqueConstraint(fields=("management", "position"), name="managed_live_target_position_unique"),
        ),
        migrations.AddConstraint(
            model_name="managedlivetarget",
            constraint=models.CheckConstraint(condition=models.Q(("position__gte", 1), ("position__lte", 3)), name="managed_live_target_position_range"),
        ),
        migrations.AddConstraint(
            model_name="managedlivetarget",
            constraint=models.CheckConstraint(condition=models.Q(("allocated_quantity__gte", 0), ("price__gt", 0), ("share_percent__gt", 0), ("share_percent__lte", 100)), name="managed_live_target_values_valid"),
        ),
    ]
