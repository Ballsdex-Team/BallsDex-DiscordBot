import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("auction_house_app", "0004_rename_max_shop_rarity"),
        ("bd_models", "0019_guildconfig_tips_enabled"),
    ]

    operations = [
        migrations.AddField(
            model_name="auctionsettings",
            name="shop_listing_hours",
            field=models.PositiveIntegerField(
                default=72,
                help_text="How long a card stays in Buggy's resale shop before it expires. Unsold cards are "
                "deleted for good when this runs out, not held back for the giveaway.",
            ),
        ),
        migrations.AddField(
            model_name="auctionsettings",
            name="excluded_balls",
            field=models.ManyToManyField(
                blank=True,
                related_name="auction_excluded",
                to="bd_models.ball",
                help_text="Treasures that can never be sold to Buggy or listed for auction, regardless of "
                "rarity (e.g. utility/token balls).",
            ),
        ),
        migrations.DeleteModel(name="DirectSaleLog"),
        migrations.CreateModel(
            name="DirectSaleRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("server_id", models.BigIntegerField(help_text="Server the /treasures sell command was used in.")),
                (
                    "ball_name",
                    models.CharField(
                        max_length=64, help_text="Name of the treasure sold (snapshot, in case it changes)."
                    ),
                ),
                ("price", models.PositiveBigIntegerField(help_text="What Buggy paid for it.")),
                ("sold_at", models.DateTimeField(auto_now_add=True)),
                (
                    "player",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="auction_direct_sales",
                        to="bd_models.player",
                    ),
                ),
            ],
            options={
                "db_table": "auctiondirectsalerecord",
                "managed": True,
                "indexes": [models.Index(fields=["player", "sold_at"], name="auctiondsr_player__sold_idx")],
            },
        ),
        migrations.CreateModel(
            name="AuctionAdminRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("server_id", models.BigIntegerField(help_text="Discord server ID this role applies to.")),
                ("role_id", models.BigIntegerField(help_text="Role ID allowed to create Featured Auctions.")),
            ],
            options={
                "db_table": "auctionadminrole",
                "managed": True,
                "unique_together": {("server_id", "role_id")},
                "indexes": [models.Index(fields=["server_id"], name="auctionadminrole_server_idx")],
            },
        ),
        migrations.CreateModel(
            name="AuctionBidBlacklist",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("discord_id", models.BigIntegerField(unique=True)),
                ("reason", models.TextField(blank=True, default=None, null=True)),
            ],
            options={"db_table": "auctionbidblacklist", "managed": True},
        ),
        migrations.CreateModel(
            name="AuctionBidBlacklistRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("server_id", models.BigIntegerField(help_text="Discord server ID this role applies to.")),
                ("role_id", models.BigIntegerField(help_text="Role ID blocked from bidding.")),
            ],
            options={
                "db_table": "auctionbidblacklistrole",
                "managed": True,
                "unique_together": {("server_id", "role_id")},
                "indexes": [models.Index(fields=["server_id"], name="auctionbidbl_server_idx")],
            },
        ),
        migrations.CreateModel(
            name="FeaturedAuction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=100)),
                ("server_id", models.BigIntegerField(help_text="Server this auction was created in.")),
                ("channel_id", models.BigIntegerField(help_text="Channel the live embed is posted in.")),
                (
                    "message_id",
                    models.BigIntegerField(blank=True, null=True, help_text="Message ID of the live embed."),
                ),
                ("min_bid_increment", models.PositiveBigIntegerField(default=1)),
                ("starting_bid", models.PositiveBigIntegerField()),
                ("current_bid", models.PositiveBigIntegerField(blank=True, null=True)),
                ("bid_count", models.PositiveIntegerField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("sold", "Sold"),
                            ("cancelled", "Cancelled"),
                            ("expired_unsold", "Expired unsold"),
                        ],
                        default="active",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                (
                    "creator",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="featured_auctions_created",
                        to="bd_models.player",
                    ),
                ),
                (
                    "current_bidder",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="featured_auctions_leading",
                        to="bd_models.player",
                    ),
                ),
            ],
            options={
                "db_table": "auctionfeatured",
                "managed": True,
                "indexes": [models.Index(fields=["status", "expires_at"], name="auctionfeat_status__expires_idx")],
            },
        ),
        migrations.CreateModel(
            name="FeaturedAuctionItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "auction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="auction_house_app.featuredauction",
                    ),
                ),
                (
                    "instance",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="featured_auction_item",
                        to="bd_models.ballinstance",
                    ),
                ),
            ],
            options={"db_table": "auctionfeatureditem", "managed": True},
        ),
        migrations.CreateModel(
            name="FeaturedAuctionBid",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.PositiveBigIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "auction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bids",
                        to="auction_house_app.featuredauction",
                    ),
                ),
                (
                    "bidder",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="featured_auction_bids",
                        to="bd_models.player",
                    ),
                ),
            ],
            options={
                "db_table": "auctionfeaturedbid",
                "managed": True,
                "indexes": [models.Index(fields=["auction", "created_at"], name="auctionfeatbid_auction__created_idx")],
            },
        ),
    ]
