import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

QUEST_TYPES = [
    ("catch", "Catch treasures"),
    ("obtain", "Obtain treasures (catch, trade, pack, craft...)"),
    ("command", "Use a command"),
    ("trade", "Complete trades"),
    ("trade_treasures", "Exchange treasures in trades"),
    ("friend", "Add friends"),
    ("battle_win", "Win battles"),
    ("give_currency", "Give berries to players"),
    ("receive_currency", "Receive berries from players"),
    ("catch_currency", "Earn berries by catching treasures"),
    ("spend_currency", "Spend berries"),
    ("craft", "Craft (claim a collector card)"),
    ("pack_buy", "Buy packs"),
    ("merchant_buy", "Buy from the merchant"),
    ("shop_buy", "Buy from Buggy's shop"),
    ("sell", "Sell treasures to Buggy"),
    ("auction_create", "List treasures on the auction house"),
    ("auction_bid", "Place bids on the auction house"),
    ("auction_won", "Win auctions"),
]
MEASURES = [("count", "Number of times"), ("amount", "Total berries")]
RESETS = [("none", "Once for the whole event"), ("daily", "Every day"), ("weekly", "Every week")]
LOGIC = [("all", "All required"), ("any", "Any one required")]
REWARD_KINDS = [("berries", "Berries"), ("treasure", "Treasure")]
BONUS_MODES = [("random", "Random, like a catch"), ("fixed", "The values set below"), ("zero", "No bonus (+0%)")]
REQUIREMENT_KINDS = [
    ("quests_all", "Complete these quests"),
    ("quests_count", "Complete a number of quests of the previous tiers"),
    ("previous_tier", "Unlock the previous tier"),
    ("own_treasures", "Own treasures (tokens, a special...)"),
    ("currency", "Have berries"),
    ("date", "Wait until a date"),
]
SOURCES = [("quest", "Quest"), ("tier", "Tier"), ("final", "End of the pass")]
STATUSES = [
    ("draft", "Draft (only staff can see it)"),
    ("active", "Active"),
    ("archived", "Archived (over, nothing can be claimed)"),
]


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("bd_models", "__first__"),
        ("collector_app", "__first__"),
        ("currency_app", "__first__"),
        ("merchant_app", "__first__"),
    ]

    operations = [
        migrations.CreateModel(
            name="Reward",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "name",
                    models.CharField(
                        help_text="Internal name, so the bundle can be reused.", max_length=64, unique=True
                    ),
                ),
                (
                    "message",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Shown to the player when they claim it. Leave empty for the default text.",
                    ),
                ),
                ("emoji", models.CharField(blank=True, default="", max_length=64)),
            ],
            options={"db_table": "eventpassreward", "ordering": ("name",), "managed": True},
        ),
        migrations.CreateModel(
            name="EventPass",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=64, unique=True)),
                ("emoji", models.CharField(blank=True, default="", max_length=64)),
                ("description", models.TextField(blank=True, default="", help_text="Shown at the top of the pass.")),
                (
                    "banner",
                    models.ImageField(
                        blank=True, help_text="Optional banner image.", max_length=200, null=True, upload_to=""
                    ),
                ),
                (
                    "colour",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Accent colour of the pass, like #E63946. Optional.",
                        max_length=7,
                    ),
                ),
                ("status", models.CharField(choices=STATUSES, default="draft", max_length=8)),
                ("starts_at", models.DateTimeField(help_text="Nothing progresses before this date.")),
                ("ends_at", models.DateTimeField(help_text="Quests stop progressing after this date.")),
                (
                    "claim_until",
                    models.DateTimeField(
                        blank=True,
                        help_text="Players can still claim what they finished until this date. Leave empty to stop "
                        "with the event.",
                        null=True,
                    ),
                ),
                (
                    "main_server_id",
                    models.BigIntegerField(
                        blank=True, help_text="Discord ID of the main server, for the quests limited to it.", null=True
                    ),
                ),
                (
                    "main_server_only",
                    models.BooleanField(
                        default=False,
                        help_text="Only count what players do in the main server. Quests can also ask for it one "
                        "by one.",
                    ),
                ),
                (
                    "final_message",
                    models.TextField(blank=True, default="", help_text="Shown when the pass is completed."),
                ),
                (
                    "position",
                    models.PositiveSmallIntegerField(
                        default=0, help_text="Passes are listed from the lowest position."
                    ),
                ),
                (
                    "notes",
                    models.TextField(blank=True, default="", help_text="Internal notes, never shown to players."),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "final_reward",
                    models.ForeignKey(
                        blank=True,
                        help_text="Given when every tier is unlocked. Leave empty if the pass has no final reward.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="eventpass_app.reward",
                    ),
                ),
            ],
            options={
                "verbose_name": "event pass",
                "verbose_name_plural": "event passes",
                "db_table": "eventpass",
                "ordering": ("position", "-starts_at"),
                "managed": True,
            },
        ),
        migrations.CreateModel(
            name="PassTier",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=64)),
                ("emoji", models.CharField(blank=True, default="", max_length=64)),
                ("description", models.TextField(blank=True, default="")),
                (
                    "position",
                    models.PositiveSmallIntegerField(default=0, help_text="Tiers are listed from the lowest position."),
                ),
                (
                    "unlock_logic",
                    models.CharField(
                        choices=LOGIC,
                        default="all",
                        help_text="Whether every requirement below is needed, or only one of them.",
                        max_length=3,
                    ),
                ),
                (
                    "locked_message",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Shown while the tier is locked. Leave empty for the generated text.",
                    ),
                ),
                (
                    "event_pass",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="tiers", to="eventpass_app.eventpass"
                    ),
                ),
                (
                    "reward",
                    models.ForeignKey(
                        blank=True,
                        help_text="Optional reward given for unlocking the tier itself.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="eventpass_app.reward",
                    ),
                ),
            ],
            options={
                "db_table": "eventpasstier",
                "ordering": ("event_pass__position", "position", "pk"),
                "managed": True,
                "unique_together": {("event_pass", "name")},
            },
        ),
        migrations.CreateModel(
            name="Quest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=64)),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Shown to players. Leave empty to use the goal generated from the settings.",
                    ),
                ),
                ("emoji", models.CharField(blank=True, default="", max_length=64)),
                (
                    "thumbnail",
                    models.ImageField(
                        blank=True, help_text="128x128 PNG image", max_length=200, null=True, upload_to=""
                    ),
                ),
                (
                    "position",
                    models.PositiveSmallIntegerField(
                        default=0, help_text="Quests are listed from the lowest position."
                    ),
                ),
                (
                    "enabled",
                    models.BooleanField(default=True, help_text="Uncheck to hide the quest without deleting it."),
                ),
                (
                    "hidden",
                    models.BooleanField(
                        default=False, help_text="Secret quest: players only see it once they completed it."
                    ),
                ),
                ("type", models.CharField(choices=QUEST_TYPES, max_length=24)),
                (
                    "target",
                    models.PositiveBigIntegerField(
                        default=1, help_text="How much progress is needed.", verbose_name="goal"
                    ),
                ),
                (
                    "measure",
                    models.CharField(
                        choices=MEASURES,
                        default="count",
                        help_text="Whether the goal counts actions or adds up berries.",
                        max_length=8,
                    ),
                ),
                (
                    "reset",
                    models.CharField(
                        choices=RESETS, default="none", help_text="How often the quest comes back.", max_length=8
                    ),
                ),
                (
                    "claim_required",
                    models.BooleanField(
                        default=True,
                        help_text="Players press a button to get the reward. Uncheck to give it as soon as they "
                        "finish.",
                    ),
                ),
                (
                    "starts_at",
                    models.DateTimeField(
                        blank=True, help_text="Optional, defaults to the start of the pass.", null=True
                    ),
                ),
                (
                    "ends_at",
                    models.DateTimeField(blank=True, help_text="Optional, defaults to the end of the pass.", null=True),
                ),
                (
                    "completion_message",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Shown when the quest is completed. Leave empty for the default text.",
                    ),
                ),
                (
                    "any_special",
                    models.BooleanField(
                        default=False,
                        help_text="Only count treasures with a special, whichever it is. Ignored if a special is set.",
                    ),
                ),
                (
                    "min_rarity",
                    models.FloatField(
                        blank=True,
                        help_text="Only count treasures at least this rare (the rarity value, 0 to 1).",
                        null=True,
                    ),
                ),
                (
                    "max_rarity",
                    models.FloatField(blank=True, help_text="Only count treasures up to this rarity value.", null=True),
                ),
                (
                    "min_attack_bonus",
                    models.IntegerField(blank=True, help_text="Minimum attack bonus, in percent.", null=True),
                ),
                (
                    "min_health_bonus",
                    models.IntegerField(blank=True, help_text="Minimum health bonus, in percent.", null=True),
                ),
                (
                    "hex_contains",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Only count treasures whose ID contains this text (hex).",
                        max_length=16,
                    ),
                ),
                (
                    "max_catch_seconds",
                    models.FloatField(
                        blank=True,
                        help_text="Only count catches made within this many seconds after the spawn.",
                        null=True,
                    ),
                ),
                (
                    "main_server_only",
                    models.BooleanField(default=False, help_text="Only count what the player does in the main server."),
                ),
                (
                    "partner_discord_id",
                    models.BigIntegerField(
                        blank=True, help_text="Only count actions involving this Discord user (ID).", null=True
                    ),
                ),
                (
                    "min_currency",
                    models.PositiveBigIntegerField(
                        blank=True, help_text="Each action must move at least this many berries to count.", null=True
                    ),
                ),
                (
                    "must_receive_treasure",
                    models.BooleanField(
                        default=False, help_text="Only count trades where the player receives at least one treasure."
                    ),
                ),
                (
                    "in_one_trade",
                    models.BooleanField(
                        default=False,
                        help_text="Ask for a single trade exchanging that many treasures, instead of a total.",
                    ),
                ),
                (
                    "command_name",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text='Full name of the slash command, without the slash: "treasures list" to open the '
                        "inventory.",
                        max_length=64,
                    ),
                ),
                (
                    "notes",
                    models.TextField(blank=True, default="", help_text="Internal notes, never shown to players."),
                ),
                (
                    "ball",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="bd_models.ball",
                    ),
                ),
                (
                    "collector",
                    models.ForeignKey(
                        blank=True,
                        help_text="Only count crafts of this collector. Leave empty for any.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="collector_app.collector",
                    ),
                ),
                (
                    "event_pass",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="quests", to="eventpass_app.eventpass"
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="bd_models.ballgroup",
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        blank=True,
                        help_text="Only count this pack. Leave empty for any pack.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="currency_app.item",
                    ),
                ),
                (
                    "merchant_item",
                    models.ForeignKey(
                        blank=True,
                        help_text="Only count this merchant item. Leave empty for any item.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="merchant_app.merchantitem",
                    ),
                ),
                (
                    "reward",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="quests",
                        to="eventpass_app.reward",
                    ),
                ),
                (
                    "special",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="bd_models.special",
                    ),
                ),
                (
                    "tier",
                    models.ForeignKey(
                        blank=True,
                        help_text="Leave empty for a quest available as soon as the pass starts.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="quests",
                        to="eventpass_app.passtier",
                    ),
                ),
                (
                    "tier_level",
                    models.ForeignKey(
                        blank=True,
                        help_text='Only count crafts of this kind ("Craft", "Elemental"...). Leave empty for any.',
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="collector_app.collectortierlevel",
                        verbose_name="craft type",
                    ),
                ),
            ],
            options={
                "db_table": "eventpassquest",
                "ordering": ("event_pass__position", "tier__position", "position", "pk"),
                "managed": True,
                "unique_together": {("event_pass", "name")},
            },
        ),
        migrations.CreateModel(
            name="RewardLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=REWARD_KINDS, default="treasure", max_length=16)),
                ("position", models.PositiveSmallIntegerField(default=0)),
                ("amount", models.PositiveBigIntegerField(default=0, help_text="Berries given, for a berry line.")),
                (
                    "quantity",
                    models.PositiveSmallIntegerField(default=1, help_text="How many copies of the treasure are given."),
                ),
                (
                    "frame_key",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text='Frame given to the treasure, as its key in the Frames section ("09-20-2026", or '
                        '"09-20-2026:3" for a frame of one special). Leave empty for a normal card.',
                        max_length=32,
                    ),
                ),
                ("bonus_mode", models.CharField(choices=BONUS_MODES, default="random", max_length=8)),
                ("attack_bonus", models.IntegerField(default=0, help_text="Used when the bonuses are fixed.")),
                ("health_bonus", models.IntegerField(default=0, help_text="Used when the bonuses are fixed.")),
                (
                    "tradeable",
                    models.BooleanField(
                        default=True,
                        help_text="Uncheck to give a treasure nobody can trade, sell or auction, whatever its usual "
                        "rules.",
                    ),
                ),
                (
                    "ball",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to="bd_models.ball"
                    ),
                ),
                (
                    "reward",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="eventpass_app.reward"
                    ),
                ),
                (
                    "special",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="bd_models.special"
                    ),
                ),
            ],
            options={"db_table": "eventpassrewardline", "ordering": ("position", "pk"), "managed": True},
        ),
        migrations.CreateModel(
            name="TierRequirement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=REQUIREMENT_KINDS, max_length=16)),
                (
                    "count",
                    models.PositiveIntegerField(
                        default=0, help_text="How many quests, treasures or berries are needed, depending on the kind."
                    ),
                ),
                ("date", models.DateTimeField(blank=True, help_text="The tier opens at this date.", null=True)),
                (
                    "ball",
                    models.ForeignKey(
                        blank=True,
                        help_text="The treasure players must own.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="bd_models.ball",
                    ),
                ),
                (
                    "quests",
                    models.ManyToManyField(
                        blank=True,
                        help_text="The quests to complete, for that kind of requirement.",
                        related_name="unlocks",
                        to="eventpass_app.quest",
                    ),
                ),
                (
                    "special",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="bd_models.special"
                    ),
                ),
                (
                    "tier",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="requirements",
                        to="eventpass_app.passtier",
                    ),
                ),
            ],
            options={"db_table": "eventpasstierrequirement", "ordering": ("pk",), "managed": True},
        ),
        migrations.CreateModel(
            name="PlayerPass",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("final_claimed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "event_pass",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="players",
                        to="eventpass_app.eventpass",
                    ),
                ),
                (
                    "player",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="event_passes", to="bd_models.player"
                    ),
                ),
            ],
            options={
                "db_table": "eventpassplayer",
                "managed": True,
                "indexes": [models.Index(fields=["event_pass"], name="eventpass_player_pass_idx")],
                "unique_together": {("player", "event_pass")},
            },
        ),
        migrations.CreateModel(
            name="PlayerQuest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "period",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text='Empty for a one-off quest, "2026-09-20" for a daily one.',
                        max_length=16,
                    ),
                ),
                ("progress", models.PositiveBigIntegerField(default=0)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "player",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="event_pass_quests",
                        to="bd_models.player",
                    ),
                ),
                (
                    "quest",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="progress", to="eventpass_app.quest"
                    ),
                ),
            ],
            options={
                "db_table": "eventpassplayerquest",
                "managed": True,
                "indexes": [
                    models.Index(fields=["player", "quest"], name="eventpass_pq_player_idx"),
                    models.Index(fields=["quest", "completed_at"], name="eventpass_pq_done_idx"),
                ],
                "unique_together": {("player", "quest", "period")},
            },
        ),
        migrations.CreateModel(
            name="RewardGrant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(choices=SOURCES, max_length=8)),
                ("source_id", models.PositiveBigIntegerField(help_text="The quest or tier the reward came from.")),
                ("period", models.CharField(blank=True, default="", max_length=16)),
                (
                    "summary",
                    models.TextField(
                        blank=True, default="", help_text="What was given, as it was shown to the player."
                    ),
                ),
                ("granted_at", models.DateTimeField(auto_now_add=True)),
                (
                    "event_pass",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="grants", to="eventpass_app.eventpass"
                    ),
                ),
                (
                    "player",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to="bd_models.player"
                    ),
                ),
                (
                    "reward",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="eventpass_app.reward",
                    ),
                ),
            ],
            options={
                "db_table": "eventpassrewardgrant",
                "managed": True,
                "indexes": [models.Index(fields=["event_pass", "granted_at"], name="eventpass_grant_idx")],
                "unique_together": {("player", "source", "source_id", "period")},
            },
        ),
        migrations.AddIndex(
            model_name="quest", index=models.Index(fields=["event_pass", "enabled"], name="eventpass_quest_pass_idx")
        ),
    ]
