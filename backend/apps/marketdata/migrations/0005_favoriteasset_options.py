from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("marketdata", "0004_favoriteasset_exchange"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="favoriteasset",
            options={"ordering": ("exchange_id", "position", "pk")},
        ),
        migrations.RenameIndex(
            model_name="favoriteasset",
            old_name="marketdata_f_owner_i_3d6133_idx",
            new_name="marketdata__owner_i_8638c0_idx",
        ),
    ]
