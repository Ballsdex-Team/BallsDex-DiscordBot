import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("achievement_app", "0005_alter_achievement_required_value_and_more"),
        ("bd_models", "0020_playerdatadeletion"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AchievementCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=64, unique=True)),
                (
                    "emoji",
                    models.CharField(
                        blank=True, default="", help_text="Optional emoji shown next to the name.", max_length=64
                    ),
                ),
                (
                    "position",
                    models.PositiveSmallIntegerField(
                        default=0, help_text="Categories are listed from the lowest position."
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "achievement categories",
                "db_table": "achievementcategory",
                "ordering": ("position", "name"),
                "managed": True,
            },
        ),
        migrations.CreateModel(
            name="PlayerAchievementStats",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "first_catch_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When the player caught a treasure themselves for the first time.",
                        null=True,
                    ),
                ),
                (
                    "player",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="achievement_stats",
                        to="bd_models.player",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "player achievement stats",
                "db_table": "achievementplayerstats",
                "managed": True,
            },
        ),
        migrations.AddField(
            model_name="achievement",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="achievements",
                to="achievement_app.achievementcategory",
            ),
        ),
        migrations.AddField(
            model_name="achievement",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft (proposal, not live)"),
                    ("active", "Active"),
                    ("retired", "Retired (can't be unlocked anymore)"),
                ],
                default="active",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="achievement",
            name="hidden",
            field=models.BooleanField(
                default=False, help_text="Secret achievement: players only see its name and description once unlocked."
            ),
        ),
        migrations.AddField(
            model_name="achievement",
            name="position",
            field=models.PositiveIntegerField(default=0, help_text="Achievements are listed from the lowest position."),
        ),
        migrations.AddField(
            model_name="achievement",
            name="any_special",
            field=models.BooleanField(
                default=False,
                help_text="Only count treasures with a special, whichever it is. Ignored if a special is set.",
            ),
        ),
        migrations.AddField(
            model_name="achievement",
            name="server_id",
            field=models.BigIntegerField(
                blank=True, help_text="Only count treasures caught in this Discord server (ID).", null=True
            ),
        ),
        migrations.AddField(
            model_name="achievement",
            name="min_attack_bonus",
            field=models.IntegerField(blank=True, help_text="Minimum attack bonus, in percent.", null=True),
        ),
        migrations.AddField(
            model_name="achievement",
            name="min_health_bonus",
            field=models.IntegerField(blank=True, help_text="Minimum health bonus, in percent.", null=True),
        ),
        migrations.AddField(
            model_name="achievement",
            name="hex_contains",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Only count treasures whose ID contains this text (hex).",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="achievement",
            name="max_catch_seconds",
            field=models.FloatField(
                blank=True, help_text="Only count catches made within this many seconds after the spawn.", null=True
            ),
        ),
        migrations.AddField(
            model_name="achievement",
            name="partner_discord_id",
            field=models.BigIntegerField(
                blank=True, help_text="Only count trades with this Discord user (ID).", null=True
            ),
        ),
        migrations.AddField(
            model_name="achievement",
            name="min_currency",
            field=models.PositiveBigIntegerField(
                blank=True,
                help_text="Only count trades where the player receives at least this much currency.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="achievement",
            name="must_receive_treasure",
            field=models.BooleanField(
                default=False, help_text="Only count trades where the player receives at least one treasure."
            ),
        ),
        migrations.AddField(
            model_name="achievement",
            name="time_unit",
            field=models.CharField(
                choices=[("days", "Days"), ("months", "Months"), ("years", "Years")], default="days", max_length=8
            ),
        ),
        migrations.AddField(
            model_name="achievement",
            name="notes",
            field=models.TextField(blank=True, default="", help_text="Internal notes, never shown to players."),
        ),
        migrations.AddField(
            model_name="achievement",
            name="proposed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(model_name="achievement", name="created_at", field=models.DateTimeField(null=True)),
        migrations.AddField(model_name="achievement", name="updated_at", field=models.DateTimeField(null=True)),
    ]
