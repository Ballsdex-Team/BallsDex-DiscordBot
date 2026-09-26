from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("auction_house_app", "0002_notification_channel_and_reject_status")]

    operations = [
        migrations.AddField(
            model_name="auctionsettings",
            name="max_direct_sale_rarity",
            field=models.FloatField(
                blank=True,
                null=True,
                help_text="If set, Buggy will only buy/keep cards for resale with a rarity between "
                "excluded_rarity and this value (e.g. setting 50 means Buggy only keeps cards with rarity "
                "between 0 and 50). Leave blank for no limit.",
            ),
        ),
        migrations.RemoveField(model_name="auctionsettings", name="booster_buy_discount_percent"),
        migrations.RemoveField(model_name="auctionsettings", name="booster_sell_bonus_percent"),
        migrations.RemoveField(model_name="auctionguildconfig", name="booster_role_id"),
        migrations.CreateModel(
            name="AuctionBoosterRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("server_id", models.BigIntegerField(help_text="Discord server ID this role applies to.")),
                ("role_id", models.BigIntegerField(help_text="Role ID granting this booster tier.")),
                (
                    "buy_discount_percent",
                    models.PositiveIntegerField(
                        default=5, help_text="Discount this role gets when buying from the Hotel's resale shop."
                    ),
                ),
                (
                    "sell_bonus_percent",
                    models.PositiveIntegerField(
                        default=5, help_text="Bonus this role gets when selling directly to the Hotel."
                    ),
                ),
            ],
            options={
                "db_table": "auctionboosterrole",
                "managed": True,
                "unique_together": {("server_id", "role_id")},
                "indexes": [models.Index(fields=["server_id"], name="auctionboos_server_id_idx")],
            },
        ),
    ]
