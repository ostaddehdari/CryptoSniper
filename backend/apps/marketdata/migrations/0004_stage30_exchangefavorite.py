import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def copy_favorites(apps, schema_editor):
    Favorite = apps.get_model("marketdata", "ExchangeFavorite")
    Account = apps.get_model("exchanges", "UserExchangeAccount")
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        columns = {
            c.name
            for c in connection.introspection.get_table_description(
                cursor, "marketdata_favoriteasset"
            )
        }
        # Earlier preview branches added an exchange column without sharing this graph.
        scoped = "exchange_id" in columns
        extra = ", exchange_id" if scoped else ""
        cursor.execute(
            "SELECT owner_id, symbol, position"
            + extra
            + " FROM marketdata_favoriteasset ORDER BY position,id"
        )
        rows = cursor.fetchall()
    for row in rows:
        owner, symbol, position = row[:3]
        exchanges = (
            [row[3]]
            if scoped and row[3]
            else Account.objects.filter(owner_id=owner)
            .values_list("exchange_id", flat=True)
            .distinct()
        )
        for exchange in exchanges:
            Favorite.objects.get_or_create(
                owner_id=owner,
                exchange_id=exchange,
                symbol=symbol,
                defaults={"position": position},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("marketdata", "0003_favoriteasset"),
        ("exchanges", "0008_react_connection_diagnostics"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="ExchangeFavorite",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("symbol", models.CharField(max_length=20)),
                ("position", models.PositiveSmallIntegerField(default=0)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
                    ),
                ),
                (
                    "exchange",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="exchanges.exchange"
                    ),
                ),
            ],
            options={
                "ordering": ("position", "pk"),
                "indexes": [
                    models.Index(
                        fields=["owner", "exchange", "position"], name="exchange_favorite_order"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("owner", "exchange", "symbol"),
                        name="exchange_favorite_owner_symbol",
                    )
                ],
            },
        ),
        migrations.RunPython(copy_favorites, migrations.RunPython.noop),
    ]
