from django.db import migrations

OLD_TYPES = {
    "ball_count": "own",
    "catch_ball": "obtain",
    "complete_group": "complete_group",
    "complete_trade": "trade",
    "completion_percentage": "completion",
    "fastest_catcher": "catch",
    "first_battle": "battle_win",
    "first_catch": "catch",
    "first_favorite_ball": "favorites",
    "first_friend": "friends",
    "first_special": "obtain",
    "first_trade": "trade",
    "have_friend": "friends",
    "playtime": "playtime",
    "receive_ball": "trade",
}

CATEGORIES = (
    ("Catching", "\N{FISHING POLE AND FISH}", ("catch",)),
    ("Collection", "\N{PACKAGE}", ("obtain", "own", "complete_group", "completion")),
    ("Trading", "\N{HANDSHAKE}", ("trade",)),
    ("Social", "\N{SPEECH BALLOON}", ("friends", "favorites")),
    ("Battles", "\N{CROSSED SWORDS}\N{VARIATION SELECTOR-16}", ("battle_win",)),
    ("Playtime", "\N{HOURGLASS WITH FLOWING SAND}", ("playtime",)),
)

FIRST_CATCHES_SQL = """
INSERT INTO achievementplayerstats (player_id, first_catch_at)
SELECT catcher_id, MIN(catch_date)
FROM (
    SELECT
        bi.catch_date,
        -- a traded treasure was caught by the player who gave it away first
        COALESCE(
            (
                SELECT tobj.player_id
                FROM tradeobject tobj
                JOIN trade t ON t.id = tobj.trade_id
                WHERE tobj.ballinstance_id = bi.id
                ORDER BY t.date, tobj.id
                LIMIT 1
            ),
            bi.player_id
        ) AS catcher_id
    FROM ballinstance bi
    WHERE bi.spawned_time IS NOT NULL
) AS caught
GROUP BY catcher_id
ON CONFLICT (player_id) DO NOTHING
"""


def convert_achievements(apps, schema_editor):
    """
    Every existing achievement keeps its ID, players' progress and rewards: only its type and settings move to the
    new explicit fields. Achievements are sorted into categories by type.
    """
    Achievement = apps.get_model("achievement_app", "Achievement")
    AchievementCategory = apps.get_model("achievement_app", "AchievementCategory")

    category_by_type = {}
    for position, (name, emoji, types) in enumerate(CATEGORIES, start=1):
        category = AchievementCategory.objects.create(name=name, emoji=emoji, position=position)
        category_by_type.update(dict.fromkeys(types, category))

    positions: dict[int, int] = {}
    for achievement in Achievement.objects.order_by("type", "target_value", "id"):
        old_type = achievement.type
        params = achievement.extra_params or {}
        achievement.type = OLD_TYPES.get(old_type, "obtain")
        if old_type not in OLD_TYPES:
            # unknown or unused types ("actions") can't progress anymore, they wait for an admin as drafts
            achievement.status = "draft"

        if old_type == "catch_ball":
            if params.get("server_id"):
                achievement.server_id = int(params["server_id"])
            if params.get("hex_contains"):
                achievement.hex_contains = str(params["hex_contains"])
            if params.get("attack_bonus") is not None:
                achievement.min_attack_bonus = int(params["attack_bonus"])
            if params.get("health_bonus") is not None:
                achievement.min_health_bonus = int(params["health_bonus"])
        elif old_type == "first_special":
            # without a special, the old first special achievement accepted any of them
            achievement.any_special = achievement.special_id is None
        elif old_type == "fastest_catcher" and achievement.required_value is not None:
            achievement.max_catch_seconds = float(achievement.required_value)
        elif old_type == "complete_trade" and params.get("requires_currency") and achievement.required_value:
            achievement.min_currency = achievement.required_value
        elif old_type == "receive_ball" and params.get("user_id"):
            achievement.partner_discord_id = int(params["user_id"])
            achievement.must_receive_treasure = True
        elif old_type == "playtime":
            achievement.time_unit = params.get("unit") or "months"

        category = category_by_type[achievement.type]
        positions[category.pk] = positions.get(category.pk, 0) + 1
        achievement.category = category
        achievement.position = positions[category.pk]
        achievement.save()


def backfill_first_catches(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(FIRST_CATCHES_SQL)


class Migration(migrations.Migration):
    dependencies = [("achievement_app", "0006_achievements_v2"), ("bd_models", "0020_playerdatadeletion")]

    operations = [
        migrations.RunPython(convert_achievements, migrations.RunPython.noop),
        migrations.RunPython(backfill_first_catches, migrations.RunPython.noop),
    ]
