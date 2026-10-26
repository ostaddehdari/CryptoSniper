# fmt: off
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_stage23_trailing_trigger_choices"),
    ]

    operations = [
        migrations.CreateModel(
            name="WalletConnection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(choices=[("metamask", "MetaMask"), ("trust_wallet", "Trust Wallet"), ("walletconnect", "WalletConnect"), ("ledger", "Ledger"), ("trezor", "Trezor"), ("evm_address", "EVM Address"), ("tron_address", "TRON Address")], max_length=24)),
                ("network", models.CharField(default="ethereum", max_length=40)),
                ("label", models.CharField(max_length=80)),
                ("address", models.CharField(max_length=160)),
                ("status", models.CharField(choices=[("watch_only", "فقط مشاهده"), ("connected", "متصل در مرورگر"), ("disabled", "غیرفعال")], default="watch_only", max_length=16)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddConstraint(
            model_name="walletconnection",
            constraint=models.UniqueConstraint(fields=("owner", "provider", "network", "address"), name="wallet_connection_owner_provider_address_unique"),
        ),
        migrations.AddIndex(
            model_name="walletconnection",
            index=models.Index(fields=["owner", "status"], name="accounts_wa_owner_i_b59cb8_idx"),
        ),
    ]
# fmt: on
