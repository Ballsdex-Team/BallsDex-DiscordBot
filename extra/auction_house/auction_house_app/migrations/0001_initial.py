import django.db.models.deletion
from django.db import migrations, models
from django.db.models import F, Q


def seed_stat_bonus_modifiers(apps, schema_editor):
    StatBonusModifier = apps.get_model("auction_house_app", "StatBonusModifier")
    StatBonusModifier.objects.bulk_create([StatBonusModifier(value=value, percent=value) for value in range(-40, 41)])


def unseed_stat_bonus_modifiers(apps, schema_editor):
    # nothing to be done, model deletion will result in row deletion anyway
    pass


class Migration(migrations.Migration):
    initial = True

    dependencies = [("bd_models", "0019_guildconfig_tips_enabled")]

    operations = [
        migrations.CreateModel(
            name="AuctionSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "base_price",
                    models.PositiveBigIntegerField(
                        default=70000,
                        help_text="Reference price used by the pricing formula. Kept for parity with the "
                        "original pricing tool this formula was ported from.",
                    ),
                ),
                (
                    "min_price",
                    models.PositiveBigIntegerField(
                        default=200,
                        help_text="Floor applied to the computed price of any card (the most common cards).",
                    ),
                ),
                (
                    "max_price",
                    models.PositiveBigIntegerField(
                        default=300000,
                        help_text="Cap applied to the computed price of any card (the rarest cards, T1).",
                    ),
                ),
                (
                    "excluded_rarity",
                    models.FloatField(
                        default=0.0,
                        help_text="Cards with this exact rarity value can never be sold to the Hotel or listed "
                        "for auction.",
                    ),
                ),
                (
                    "direct_sale_daily_limit",
                    models.PositiveIntegerField(
                        default=10, help_text="Maximum number of cards a player can sell directly to the Hotel per day."
                    ),
                ),
                (
                    "max_active_listings",
                    models.PositiveIntegerField(
                        default=5, help_text="Maximum number of cards a player can have listed for auction at once."
                    ),
                ),
                (
                    "resale_markup_percent",
                    models.PositiveIntegerField(
                        default=10,
                        help_text="Markup applied when the Hotel relists a card it bought directly from a player.",
                    ),
                ),
                (
                    "min_listing_hours",
                    models.PositiveIntegerField(
                        default=1, help_text="Minimum duration a player can choose when listing a card for auction."
                    ),
                ),
                (
                    "max_listing_hours",
                    models.PositiveIntegerField(
                        default=72, help_text="Maximum duration a player can choose when listing a card for auction."
                    ),
                ),
                (
                    "giveaway_interval_hours",
                    models.PositiveIntegerField(
                        default=12, help_text="How often the Hotel raffles off one of its unsold cards, per server."
                    ),
                ),
                (
                    "giveaway_activity_window_hours",
                    models.PositiveIntegerField(
                        default=24,
                        help_text="A player must have used a bot command within this window to be eligible to win.",
                    ),
                ),
                (
                    "booster_buy_discount_percent",
                    models.PositiveIntegerField(
                        default=5, help_text="Discount boosters get when buying from the Hotel's resale shop."
                    ),
                ),
                (
                    "booster_sell_bonus_percent",
                    models.PositiveIntegerField(
                        default=5, help_text="Bonus boosters get when selling directly to the Hotel."
                    ),
                ),
            ],
            options={
                "db_table": "auctionsettings",
                "managed": True,
                "constraints": [
                    models.CheckConstraint(
                        condition=Q(("min_price__lte", F("max_price"))), name="auctionsettings_price_min_lte_max"
                    ),
                    models.CheckConstraint(
                        condition=Q(("min_listing_hours__lte", F("max_listing_hours"))),
                        name="auctionsettings_listing_hours_min_lte_max",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="AuctionGuildConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "server_id",
                    models.BigIntegerField(help_text="Discord server ID this configuration applies to.", unique=True),
                ),
                (
                    "booster_role_id",
                    models.BigIntegerField(
                        blank=True,
                        null=True,
                        help_text="Role ID granting the booster discount/bonus on Hotel transactions.",
                    ),
                ),
            ],
            options={"db_table": "auctionguildconfig", "managed": True},
        ),
        migrations.CreateModel(
            name="SpecialPriceModifier",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "percent",
                    models.IntegerField(default=0, help_text="Price bonus/malus for this special, in percent."),
                ),
                (
                    "special",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="auction_price_modifier",
                        to="bd_models.special",
                    ),
                ),
            ],
            options={"db_table": "auctionspecialpricemodifier", "managed": True},
        ),
        migrations.CreateModel(
            name="StatBonusModifier",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("value", models.IntegerField(help_text="Average of a card's attack and health bonus.", unique=True)),
                (
                    "percent",
                    models.IntegerField(
                        default=0, help_text="Price bonus/malus applied for this stat average, in percent."
                    ),
                ),
            ],
            options={
                "db_table": "auctionstatbonusmodifier",
                "managed": True,
                "ordering": ["value"],
                "constraints": [
                    models.CheckConstraint(
                        condition=Q(("value__gte", -40)) & Q(("value__lte", 40)), name="auctionstatbonusmodifier_range"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="AuctionListing",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("server_id", models.BigIntegerField()),
                ("asking_price", models.PositiveBigIntegerField()),
                ("duration_hours", models.PositiveIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("sold", "Sold"),
                            ("expired", "Expired"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="active",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                (
                    "instance",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="auction_listing",
                        to="bd_models.ballinstance",
                    ),
                ),
                (
                    "seller",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="auction_listings",
                        to="bd_models.player",
                    ),
                ),
            ],
            options={
                "db_table": "auctionlisting",
                "managed": True,
                "indexes": [
                    models.Index(fields=["server_id", "status"], name="auctionlist_server__status_idx"),
                    models.Index(fields=["seller", "status"], name="auctionlist_seller__status_idx"),
                    models.Index(fields=["status", "expires_at"], name="auctionlist_status__expires_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AuctionOffer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.PositiveBigIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("accepted", "Accepted"),
                            ("cancelled", "Cancelled"),
                            ("refunded", "Refunded"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "buyer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="auction_offers",
                        to="bd_models.player",
                    ),
                ),
                (
                    "listing",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="offers",
                        to="auction_house_app.auctionlisting",
                    ),
                ),
            ],
            options={
                "db_table": "auctionoffer",
                "managed": True,
                "indexes": [
                    models.Index(fields=["listing", "status"], name="auctionoffer_listing__status_idx"),
                    models.Index(fields=["buyer", "status"], name="auctionoffer_buyer__status_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="HotelStock",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("server_id", models.BigIntegerField()),
                ("buyout_price", models.PositiveBigIntegerField(help_text="What the Hotel paid the original seller.")),
                ("resale_price", models.PositiveBigIntegerField(help_text="Price the Hotel resells this card for.")),
                (
                    "status",
                    models.CharField(
                        choices=[("available", "Available"), ("sold", "Sold"), ("given_away", "Given away")],
                        default="available",
                        max_length=16,
                    ),
                ),
                ("acquired_at", models.DateTimeField(auto_now_add=True)),
                (
                    "instance",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="hotel_stock",
                        to="bd_models.ballinstance",
                    ),
                ),
            ],
            options={
                "db_table": "auctionhotelstock",
                "managed": True,
                "indexes": [models.Index(fields=["server_id", "status"], name="auctionhotel_server__status_idx")],
            },
        ),
        migrations.CreateModel(
            name="DirectSaleLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("server_id", models.BigIntegerField()),
                ("sale_date", models.DateField()),
                ("count", models.PositiveIntegerField(default=0)),
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
                "db_table": "auctiondirectsalelog",
                "managed": True,
                "unique_together": {("player", "server_id", "sale_date")},
            },
        ),
        migrations.CreateModel(
            name="ServerActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("server_id", models.BigIntegerField()),
                ("last_seen", models.DateTimeField(auto_now=True)),
                (
                    "player",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="auction_activity",
                        to="bd_models.player",
                    ),
                ),
            ],
            options={
                "db_table": "auctionserveractivity",
                "managed": True,
                "unique_together": {("player", "server_id")},
                "indexes": [models.Index(fields=["server_id", "last_seen"], name="auctionactiv_server__lastseen_idx")],
            },
        ),
        migrations.CreateModel(
            name="GiveawayLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("server_id", models.BigIntegerField()),
                ("drawn_at", models.DateTimeField(auto_now_add=True)),
                (
                    "instance",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="auction_giveaway_logs",
                        to="bd_models.ballinstance",
                    ),
                ),
                (
                    "winner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="auction_giveaway_wins",
                        to="bd_models.player",
                    ),
                ),
            ],
            options={
                "db_table": "auctiongiveawaylog",
                "managed": True,
                "indexes": [models.Index(fields=["server_id", "drawn_at"], name="auctiongive_server__drawn_idx")],
            },
        ),
        migrations.RunPython(seed_stat_bonus_modifiers, unseed_stat_bonus_modifiers),
    ]
