import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("bd_models", "0020_playerdatadeletion"), ("collector_app", "0004_alter_collector_ball")]

    operations = [
        migrations.CreateModel(
            name="CollectorSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "monitoring_enabled",
                    models.BooleanField(
                        default=True,
                        help_text="Watch the collector cards of monitored tiers: when their owner stops meeting the "
                        "requirements (traded, gave or sold a required treasure), a timer starts and the card is "
                        "taken back once it runs out.",
                    ),
                ),
                (
                    "grace_period_hours",
                    models.PositiveIntegerField(
                        default=48,
                        help_text="How long a player has to get the missing treasures back before losing the card.",
                    ),
                ),
            ],
            options={"db_table": "collectorsettings", "managed": True, "verbose_name_plural": "collector settings"},
        ),
        migrations.CreateModel(
            name="CollectorTierLevel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "name",
                    models.CharField(help_text='Name shown to players, like "Tier 2".', max_length=32, unique=True),
                ),
                (
                    "position",
                    models.PositiveSmallIntegerField(default=1, help_text="Tiers are shown from the lowest position."),
                ),
                (
                    "emoji",
                    models.CharField(
                        blank=True, default="", help_text="Optional emoji shown on the claim button.", max_length=64
                    ),
                ),
                (
                    "claimable",
                    models.BooleanField(
                        default=True,
                        help_text="Uncheck to prevent players from claiming this tier on every collector, for instance "
                        "while its requirements are being set up.",
                    ),
                ),
                (
                    "monitored",
                    models.BooleanField(
                        default=True,
                        help_text="Cards of this tier claimed from now on are taken back if their owner stops meeting "
                        "the requirements for too long. Cards claimed before this option was enabled are never "
                        "watched.",
                    ),
                ),
                (
                    "special",
                    models.ForeignKey(
                        blank=True,
                        help_text="Special given to the cards of this tier, unless a collector sets another one.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="bd_models.special",
                    ),
                ),
            ],
            options={"db_table": "collectortierlevel", "managed": True, "ordering": ("position", "id")},
        ),
        migrations.CreateModel(
            name="CollectorTier",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "no_special",
                    models.BooleanField(
                        default=False,
                        help_text="The card has no special at all, the treasure itself is the collector card.",
                    ),
                ),
                ("tradeable", models.BooleanField(default=True, help_text="Whether the claimed cards can be traded.")),
                (
                    "enabled",
                    models.BooleanField(
                        default=True, help_text="Uncheck to disable this tier for this collector only."
                    ),
                ),
                (
                    "price",
                    models.PositiveBigIntegerField(
                        blank=True,
                        help_text="Optional amount of currency players must pay to claim this tier.",
                        null=True,
                    ),
                ),
                (
                    "collector",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="tiers", to="collector_app.collector"
                    ),
                ),
                (
                    "level",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="collector_tiers",
                        to="collector_app.collectortierlevel",
                    ),
                ),
                (
                    "special",
                    models.ForeignKey(
                        blank=True,
                        help_text="Leave empty to use the special of the tier.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="bd_models.special",
                    ),
                ),
            ],
            options={"db_table": "collectortier", "managed": True, "unique_together": {("collector", "level")}},
        ),
        migrations.AddField(
            model_name="collectorrequirement",
            name="level",
            field=models.ForeignKey(
                help_text="The tier this requirement belongs to.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="collector_app.collectortierlevel",
            ),
        ),
        migrations.AddField(
            model_name="collectorinstance",
            name="level",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="instances",
                to="collector_app.collectortierlevel",
            ),
        ),
        migrations.AddField(
            model_name="collectorinstance",
            name="ball_instance",
            field=models.ForeignKey(
                blank=True,
                help_text="The card.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="bd_models.ballinstance",
            ),
        ),
        migrations.AddField(
            model_name="collectorinstance", name="claimed_at", field=models.DateTimeField(blank=True, null=True)
        ),
        migrations.AddField(
            model_name="collectorinstance",
            name="monitored",
            field=models.BooleanField(
                default=False, help_text="Whether the card is taken back if its owner stops meeting the requirements."
            ),
        ),
        migrations.AddField(
            model_name="collectorinstance",
            name="at_risk_since",
            field=models.DateTimeField(
                blank=True, help_text="When the owner stopped meeting the requirements.", null=True
            ),
        ),
        migrations.AddField(
            model_name="collectorinstance",
            name="grace_ends_at",
            field=models.DateTimeField(blank=True, help_text="When the card will be taken back.", null=True),
        ),
        migrations.AddField(
            model_name="collectorinstance",
            name="revoked_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the card was taken back. The collector can then be claimed again.",
                null=True,
            ),
        ),
    ]
