from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):
    dependencies = [
        ("marketdata", "0002_historicalcandle"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FavoriteAsset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("symbol", models.CharField(max_length=20)),
                ("position", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
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
            index=models.Index(fields=["owner", "position"], name="market_fav_owner_pos_idx"),
        ),
    ]
