from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AugmentSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "rarity_cost_min",
                    models.PositiveIntegerField(
                        default=2500, help_text="Base augment cost in berries for the rarest cards (rarity value of 1)."
                    ),
                ),
                (
                    "rarity_cost_max",
                    models.PositiveIntegerField(
                        default=50,
                        help_text="Base augment cost in berries for common cards, once rarity_cost_floor_at "
                        "is reached.",
                    ),
                ),
                (
                    "rarity_cost_floor_at",
                    models.FloatField(
                        default=230.0,
                        help_text="Rarity value at which the base cost bottoms out at rarity_cost_max. "
                        "Cost decreases linearly between rarity 1 and this value.",
                    ),
                ),
                (
                    "min_roll",
                    models.PositiveIntegerField(
                        default=1,
                        help_text="Minimum stat change (percentage points) applied to each stat, win or lose.",
                    ),
                ),
                (
                    "max_roll",
                    models.PositiveIntegerField(
                        default=5,
                        help_text="Maximum stat change (percentage points) applied to each stat, win or lose.",
                    ),
                ),
                (
                    "min_success_rate",
                    models.FloatField(
                        default=0.0, help_text="Success rate (%) applied when a card's stats are already maxed out."
                    ),
                ),
                (
                    "max_success_rate",
                    models.FloatField(
                        default=100.0, help_text="Success rate (%) applied when a card's stats are at their worst."
                    ),
                ),
                (
                    "min_cost_multiplier",
                    models.FloatField(
                        default=0.5, help_text="Cost multiplier applied when a card's stats are at their worst."
                    ),
                ),
                (
                    "max_cost_multiplier",
                    models.FloatField(
                        default=2.0, help_text="Cost multiplier applied when a card's stats are already maxed out."
                    ),
                ),
            ],
            options={
                "db_table": "augmentsettings",
                "managed": True,
                "constraints": [
                    models.CheckConstraint(
                        condition=Q(("min_roll__lte", F("max_roll"))), name="augmentsettings_roll_min_lte_max"
                    ),
                    models.CheckConstraint(
                        condition=Q(("min_success_rate__gte", 0)) & Q(("max_success_rate__lte", 100)),
                        name="augmentsettings_success_rate_bounds",
                    ),
                    models.CheckConstraint(
                        condition=Q(("min_success_rate__lte", F("max_success_rate"))),
                        name="augmentsettings_success_rate_min_lte_max",
                    ),
                    models.CheckConstraint(
                        condition=Q(("rarity_cost_floor_at__gt", 1)), name="augmentsettings_rarity_cost_floor_gt_1"
                    ),
                ],
            },
        )
    ]
