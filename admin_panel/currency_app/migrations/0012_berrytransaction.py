import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("currency_app", "0011_dailybonusserver_and_multi_roles"),
        ("bd_models", "0019_guildconfig_tips_enabled"),
    ]

    operations = [
        migrations.CreateModel(
            name="BerryTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "amount",
                    models.BigIntegerField(help_text="Signed: positive credits the player, negative debits them."),
                ),
                (
                    "balance_after",
                    models.PositiveBigIntegerField(help_text="The player's balance once this change was applied."),
                ),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("unknown", "Unknown"),
                            ("daily", "Daily claim"),
                            ("give_sent", "Gave berries away"),
                            ("give_received", "Received berries"),
                            ("spawn_catch", "Caught a berry spawn"),
                            ("achievement", "Achievement reward"),
                            ("trade", "Trade"),
                            ("admin_adjust", "Admin adjustment"),
                            ("auction_sell", "Sold to Buggy"),
                            ("auction_shop_buy", "Bought from Buggy's shop"),
                            ("auction_bid_hold", "Bid placed (berries held)"),
                            ("auction_bid_refund", "Bid returned"),
                            ("auction_sale_payout", "Listing sold (payout)"),
                            ("featured_bid_hold", "Featured bid placed (berries held)"),
                            ("featured_bid_refund", "Featured bid returned"),
                            ("featured_payout", "Featured auction sold (payout)"),
                            ("pack_buy", "Bought a pack"),
                            ("merchant_buy", "Bought from the merchant"),
                            ("merchant_token", "Converted merchant tokens"),
                            ("collectible_buy", "Bought a collectible"),
                            ("augment_buy", "Bought an augment"),
                            ("battle_item_buy", "Bought a battle item"),
                            ("battle_wager_hold", "Battle wager (berries held)"),
                            ("battle_wager_refund", "Battle wager returned"),
                            ("battle_payout", "Battle winnings"),
                        ],
                        default="unknown",
                        max_length=32,
                    ),
                ),
                (
                    "description",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=256,
                        help_text="What this movement was for (item bought, listing ID, the other player, ...).",
                    ),
                ),
                (
                    "server_id",
                    models.BigIntegerField(
                        blank=True, null=True, help_text="Server the action happened in, when it came from a command."
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "player",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="berry_transactions",
                        to="bd_models.player",
                    ),
                ),
            ],
            options={
                "db_table": "berrytransaction",
                "managed": True,
                "indexes": [
                    models.Index(fields=["player", "-created_at"], name="berrytx_player__created_idx"),
                    models.Index(fields=["reason"], name="berrytx_reason_idx"),
                    models.Index(fields=["-created_at"], name="berrytx_created_idx"),
                ],
            },
        )
    ]
