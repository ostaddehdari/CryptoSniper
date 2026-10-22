from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_walletconnection"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="walletconnection",
            old_name="accounts_wa_owner_i_b59cb8_idx",
            new_name="accounts_wa_owner_i_e18d3d_idx",
        ),
    ]
