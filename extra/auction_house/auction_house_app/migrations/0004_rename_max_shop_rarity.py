from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("auction_house_app", "0003_multi_booster_roles_and_rarity_cap")]

    operations = [
        migrations.RenameField(
            model_name="auctionsettings", old_name="max_direct_sale_rarity", new_name="max_shop_rarity"
        ),
        migrations.AlterField(
            model_name="auctionsettings",
            name="max_shop_rarity",
            field=models.FloatField(
                blank=True,
                null=True,
                help_text="If set, only cards with a rarity between excluded_rarity and this value show up in "
                "Buggy's resale shop (e.g. setting 50 means the shop only lists cards with rarity between 0 and "
                "50). Buggy still buys every non-special card directly regardless of this setting — this only "
                "limits what he resells. Leave blank for no limit.",
            ),
        ),
    ]
