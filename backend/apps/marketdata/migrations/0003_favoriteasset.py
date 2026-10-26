# fmt: off
import django.db.models.deletion

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("marketdata", "0002_historicalcandle"),
    ]

    operations = [
        migrations.CreateModel(
            name="FavoriteAsset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("symbol", models.CharField(max_length=20)),
                ("position", models.PositiveSmallIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="favorite_assets", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("position", "pk")},
        ),
        migrations.AddConstraint(
            model_name="favoriteasset",
            constraint=models.UniqueConstraint(fields=("owner", "symbol"), name="favorite_asset_owner_symbol_unique"),
        ),
        migrations.AddIndex(
            model_name="favoriteasset",
            index=models.Index(fields=["owner", "position"], name="marketdata__owner_i_ec8b24_idx"),
        ),
    ]
# fmt: on
