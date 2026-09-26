from typing import TYPE_CHECKING

from django.db import migrations, models
from django.db.models import Q

if TYPE_CHECKING:
    from django.apps.registry import Apps
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor

OLD_MAX_COST_MULTIPLIER, NEW_MAX_COST_MULTIPLIER = 2.0, 4.0
OLD_MIN_SUCCESS_RATE, NEW_MIN_SUCCESS_RATE = 0.0, 10.0


def upgrade_existing_settings(apps: "Apps", schema_editor: "BaseDatabaseSchemaEditor"):
    AugmentSettings = apps.get_model("augment_app", "AugmentSettings")
    # Only touch rows still holding the pre-migration defaults, so a deliberately
    # customized settings row (via the admin panel) isn't silently overwritten.
    AugmentSettings.objects.filter(
        max_cost_multiplier=OLD_MAX_COST_MULTIPLIER, min_success_rate=OLD_MIN_SUCCESS_RATE
    ).update(max_cost_multiplier=NEW_MAX_COST_MULTIPLIER, min_success_rate=NEW_MIN_SUCCESS_RATE)


def downgrade_existing_settings(apps: "Apps", schema_editor: "BaseDatabaseSchemaEditor"):
    AugmentSettings = apps.get_model("augment_app", "AugmentSettings")
    AugmentSettings.objects.filter(
        max_cost_multiplier=NEW_MAX_COST_MULTIPLIER, min_success_rate=NEW_MIN_SUCCESS_RATE
    ).update(max_cost_multiplier=OLD_MAX_COST_MULTIPLIER, min_success_rate=OLD_MIN_SUCCESS_RATE)


class Migration(migrations.Migration):
    dependencies = [("augment_app", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="augmentsettings",
            name="high_stat_threshold",
            field=models.FloatField(
                default=30.0,
                help_text="Cumulative attack_bonus + health_bonus (%) at which a card is considered maxed out.",
            ),
        ),
        migrations.AlterField(
            model_name="augmentsettings",
            name="min_success_rate",
            field=models.FloatField(
                default=10.0, help_text="Success rate (%) applied when a card's stats are already maxed out."
            ),
        ),
        migrations.AlterField(
            model_name="augmentsettings",
            name="max_cost_multiplier",
            field=models.FloatField(
                default=4.0,
                help_text="Cost multiplier applied when a card's stats are already maxed out. "
                "Combined with rarity_cost_min, this sets the absolute maximum augment cost "
                "(e.g. 2500 * 4.0 = 10 000 berries for a maxed-out rarity-1 card).",
            ),
        ),
        migrations.AddConstraint(
            model_name="augmentsettings",
            constraint=models.CheckConstraint(
                condition=Q(("high_stat_threshold__gt", 0)), name="augmentsettings_high_stat_threshold_gt_0"
            ),
        ),
        migrations.RunPython(code=upgrade_existing_settings, reverse_code=downgrade_existing_settings, atomic=True),
    ]
