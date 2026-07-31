from typing import TYPE_CHECKING, cast

import django.db.models.deletion
from django.db import migrations, models

import bd_models.models

if TYPE_CHECKING:
    from django.apps.registry import Apps
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor

    from bd_models.models import Asset, Ball, Economy, Regime, Special


# We want to convert the assets column from text type to foreign key type, but both
# types cannot be converted automatically (how would you even do that)
# The easiest way is to perform the conversion in SQL and take benefit of the advanced
# syntax to convert the data on the fly while we're altering the column type
# https://www.postgresql.org/docs/current/sql-altertable.html#SQL-ALTERTABLE-DESC-SET-DATA-TYPE
ALTER_TYPE_QUERY_FORWARDS = """
ALTER TABLE {table_name}
    ALTER COLUMN {column_name} SET DATA TYPE bigint USING (
        SELECT asset.id FROM asset LEFT JOIN ball ON bd_models_asset.file = {column_name}
    ),
    ADD CONSTRAINT FOREIGN KEY {column_name} REFERENCES asset(id)
"""
# Preserve ability to rollback the migration
ALTER_TYPE_QUERY_BACKWARDS = """
ALTER TABLE {table_name}
    ALTER COLUMN {column_name} SET DATA TYPE character varying(200) USING (
        SELECT asset.file FROM asset LEFT JOIN ball ON bd_models_asset.id = {column_name}
    )
"""
# This is the list of table-columns that will need editing
COLUMN_LIST = [
    ("ball", "wild_card"),
    ("ball", "collection_card"),
    ("regime", "background"),
    ("economy", "icon"),
    ("special", "background"),
]

# And now we generate the list of queries to run
forward_queries = [
    ALTER_TYPE_QUERY_FORWARDS.format(table_name=table, column_name=column) for table, column in COLUMN_LIST
]
backwards_queries = [
    ALTER_TYPE_QUERY_BACKWARDS.format(table_name=table, column_name=column) for table, column in COLUMN_LIST
]


def create_assets_forward(apps: "Apps", schema_editor: "BaseDatabaseSchemaEditor"):
    ball = cast(type["Ball"], apps.get_model("bd_models", "Ball"))
    regime = cast(type["Regime"], apps.get_model("bd_models", "Regime"))
    economy = cast(type["Economy"], apps.get_model("bd_models", "Economy"))
    special = cast(type["Special"], apps.get_model("bd_models", "Special"))
    asset = cast(type["Asset"], apps.get_model("bd_models", "Asset"))

    assets: list["Asset"] = []
    for ball in ball.objects.all():
        assets.append(asset(file=ball.wild_card, author=ball.credits))
        assets.append(asset(file=ball.collection_card, author=ball.credits))
    for regime in regime.objects.all():
        assets.append(asset(file=regime.background, author="MISSING"))
    for economy in economy.objects.filter(icon__isnull=False):
        assets.append(asset(file=economy.icon, author="MISSING"))
    for special in special.objects.filter(background__isnull=False):
        assets.append(asset(file=special.background, author=special.credits))

    asset.objects.bulk_create(assets)


class Migration(migrations.Migration):
    dependencies = [("bd_models", "0018_guildconfig_manual_drop_enabled")]

    operations = [
        migrations.CreateModel(
            name="Asset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.ImageField(upload_to="", validators=[bd_models.models.filesize_validator])),
                ("author", models.CharField(help_text="Name of the asset author.", max_length=32)),
                (
                    "hidden",
                    models.BooleanField(default=False, help_text="Whether the artist should be hidden from /about"),
                ),
                ("extra_data", models.JSONField(blank=True, default=dict)),
                (
                    "player",
                    models.ForeignKey(
                        default=None,
                        help_text="The player object of the author, if it exists. Optional and unused for now.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="bd_models.player",
                    ),
                ),
            ],
        ),
        # First, fill the data in the new table
        migrations.RunPython(create_assets_forward, reverse_code=migrations.RunPython.noop),
        # Then migrate columns
        migrations.RunSQL(
            forward_queries,
            reverse_sql=backwards_queries,
            # letting Django know of our schema changes, preserving the migration autodetection
            state_operations=[
                migrations.AlterField(
                    model_name="asset",
                    name="author",
                    field=models.CharField(help_text="Name of the asset author.", max_length=64),
                ),
                migrations.AlterField(
                    model_name="ball",
                    name="collection_card",
                    field=models.ForeignKey(
                        help_text="Image used when displaying balls",
                        on_delete=django.db.models.deletion.RESTRICT,
                        related_name="collection_card_set",
                        to="bd_models.asset",
                    ),
                ),
                migrations.AlterField(
                    model_name="ball",
                    name="wild_card",
                    field=models.ForeignKey(
                        help_text="Image used when a new ball spawns in the wild",
                        on_delete=django.db.models.deletion.RESTRICT,
                        related_name="wild_card_set",
                        to="bd_models.asset",
                    ),
                ),
                migrations.AlterField(
                    model_name="economy",
                    name="icon",
                    field=models.ForeignKey(
                        help_text="512x512 PNG image",
                        on_delete=django.db.models.deletion.RESTRICT,
                        to="bd_models.asset",
                    ),
                ),
                migrations.AlterField(
                    model_name="regime",
                    name="background",
                    field=models.ForeignKey(
                        help_text="1428x2000 PNG image",
                        on_delete=django.db.models.deletion.RESTRICT,
                        to="bd_models.asset",
                    ),
                ),
                migrations.AlterField(
                    model_name="special",
                    name="background",
                    field=models.ForeignKey(
                        blank=True,
                        help_text="1428x2000 PNG image",
                        null=True,
                        on_delete=django.db.models.deletion.RESTRICT,
                        to="bd_models.asset",
                    ),
                ),
            ],
        ),
    ]
