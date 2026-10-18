from django.db import migrations

EXCHANGES = (
    ("nobitex", "Nobitex", "https://nobitex.ir/", True),
    ("lbank", "LBank", "https://www.lbank.com/", False),
    ("weex", "WEEX", "https://www.weex.com/", False),
    ("ourbit", "Ourbit", "https://www.ourbit.com/", False),
    ("bitunix", "Bitunix", "https://www.bitunix.com/", False),
)


def seed(apps, schema_editor):
    Exchange = apps.get_model("exchanges", "Exchange")
    for code, name, website, sandbox in EXCHANGES:
        Exchange.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "website": website,
                "adapter_code": code,
                "spot_supported": True,
                "margin_supported": False,
                "futures_supported": False,
                "sandbox_supported": sandbox,
                "enabled": True,
            },
        )


def unseed(apps, schema_editor):
    apps.get_model("exchanges", "Exchange").objects.filter(
        code__in=[row[0] for row in EXCHANGES]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("exchanges", "0004_alter_exchange_website")]
    operations = [migrations.RunPython(seed, unseed)]
