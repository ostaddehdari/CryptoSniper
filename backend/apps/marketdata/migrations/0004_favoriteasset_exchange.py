from django.db import migrations, models
import django.db.models.deletion


def assign_existing_favorites(apps, schema_editor):
    FavoriteAsset = apps.get_model("marketdata", "FavoriteAsset")
    UserExchangeAccount = apps.get_model("exchanges", "UserExchangeAccount")
    for favorite in FavoriteAsset.objects.filter(exchange__isnull=True).iterator():
        account = (
            UserExchangeAccount.objects.filter(
                owner_id=favorite.owner_id,
                environment="live",
                status__in=("connected", "restricted", "pending"),
            )
            .exclude(exchange__code="binance")
            .order_by("pk")
            .first()
        )
        if account:
            favorite.exchange_id = account.exchange_id
            favorite.save(update_fields=("exchange_id",))


class Migration(migrations.Migration):
    dependencies = [
        ("exchanges", "0008_environment_default_live"),
        ("marketdata", "0003_favoriteasset"),
    ]

    operations = [
        migrations.AddField(
            model_name="favoriteasset",
            name="exchange",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="favorite_assets",
                to="exchanges.exchange",
            ),
        ),
        migrations.RunPython(assign_existing_favorites, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="favoriteasset",
            name="favorite_asset_owner_symbol_unique",
        ),
        migrations.RemoveIndex(
            model_name="favoriteasset",
            name="marketdata_f_owner_i_a331cb_idx",
        ),
        migrations.AddConstraint(
            model_name="favoriteasset",
            constraint=models.UniqueConstraint(
                fields=("owner", "exchange", "symbol"),
                name="favorite_asset_owner_exchange_symbol_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="favoriteasset",
            index=models.Index(
                fields=["owner", "exchange", "position"],
                name="marketdata_f_owner_i_3d6133_idx",
            ),
        ),
    ]
