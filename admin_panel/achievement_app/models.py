from typing import Any, Awaitable, Callable

from django.db import models
from django.utils import timezone

from bd_models.models import Ball, BallGroup, Player, Special, balls, groups, specials


class AchievementType(models.TextChoices):
    FIRST_CATCH = "first_catch", "First Catch"
    FIRST_SPECIAL = "first_special", "First Special"
    FIRST_TRADE = "first_trade", "First Trade"
    FIRST_BATTLE_WIN = "first_battle", "First Battle"
    FIRST_FRIEND = "first_friend", "First Friend"
    FIRST_FAVORITE_BALL = "first_favorite_ball", "First Favorite Ball"
    CATCH_BALL = "catch_ball", "Catch Ball"
    FASTEST_CATCHER = "fastest_catcher", "Fastest Catcher"
    COMPLETE_TRADE = "complete_trade", "Complete Trade"
    RECEIVE_BALL = "receive_ball", "Receive Ball"
    BALL_COUNT = "ball_count", "Ball Count"
    COMPLETION_PERCENTAGE = "completion_percentage", "Completion Percentage"
    HAVE_FRIEND = "have_friend", "Have X Friend"
    ACTIONS = "actions", "Actions (event-triggered)"
    COMPLETE_GROUP = "complete_group", "Catch all balls from a Group"
    PLAYTIME = "playtime", "Time using the bot"


ACHIEVEMENT_TYPE_SCHEMA = {
    AchievementType.COMPLETE_TRADE: [{"name": "requires_currency", "label": "Requires Coins", "input": "checkbox"}],
    AchievementType.RECEIVE_BALL: [{"name": "user_id", "label": "User ID", "input": "text"}],
    AchievementType.CATCH_BALL: [
        {"name": "server_id", "label": "Server ID", "input": "text"},
        {"name": "hex_contains", "label": "Hex ID Contains", "input": "text"},
        {"name": "attack_bonus", "label": "Attack Bonus", "input": "number"},
        {"name": "health_bonus", "label": "Health Bonus", "input": "number"},
    ],
    AchievementType.PLAYTIME: [
        {"name": "unit", "label": "Unit", "input": "select", "options": ["days", "months", "years"]}
    ],
}

CHECKERS: dict[AchievementType, Callable[..., Awaitable[bool | int]]] = {}


def register_checker(achievement_type: AchievementType):
    """
    Register a checker for achievements.

    False = no progress
    True = increment by 1
    int = absolute progress
    """

    def decorator(func: Callable[..., Awaitable[bool | int]]) -> Callable[..., Awaitable[bool | int]]:
        if achievement_type in CHECKERS:
            raise ValueError(f"A {achievement_type.name} type checker has already been registered.")
        CHECKERS[achievement_type] = func
        return func

    return decorator


class PrerequisiteLogic(models.TextChoices):
    ALL = "all", "All required"
    ANY = "any", "Any one Required"


class Achievement(models.Model):
    name = models.CharField(max_length=64, unique=True)
    description = models.TextField(null=True, blank=True)
    thumbnail = models.ImageField(max_length=200, help_text="128x128 PNG image", null=True, blank=True)
    type = models.CharField(max_length=48, choices=AchievementType.choices)
    prerequisities: models.ManyToManyField["Achievement", Any] = models.ManyToManyField(
        "self", symmetrical=False, blank=True
    )
    prerequisite_logic = models.CharField(
        max_length=3, choices=PrerequisiteLogic.choices, default=PrerequisiteLogic.ALL
    )

    target_value = models.PositiveBigIntegerField(help_text="Total progress needed to complete this achievement")
    required_value = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Threshold each individual event must meet to count "
            "(Only for Fastest Catcher and Complete Trade with Currency)"
        ),
    )
    ball = models.ForeignKey(Ball, null=True, blank=True, on_delete=models.SET_NULL)
    ball_id: int | None
    group = models.ForeignKey(BallGroup, null=True, blank=True, on_delete=models.SET_NULL)
    group_id: int | None
    special = models.ForeignKey(Special, null=True, blank=True, on_delete=models.SET_NULL)
    special_id: int | None
    currency_reward = models.PositiveIntegerField(
        db_default=0, help_text="When a user completes the achievement, how much currency gets?"
    )

    extra_params = models.JSONField(default=dict, blank=True)

    @property
    def cached_ball(self):
        return balls.get(self.ball_id) or self.ball if self.ball_id else None

    @property
    def cached_group(self):
        return groups.get(self.group_id) or self.group if self.group_id else None

    @property
    def cached_special(self):
        return specials.get(self.special_id) or self.special if self.special_id else None

    class Meta:
        managed = True
        db_table = "achievement"


class UserAchievement(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE)
    progress = models.PositiveIntegerField(default=0)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = "userachievement"
        unique_together = (("player", "achievement"),)
        indexes = [models.Index(fields=("player_id",)), models.Index(fields=("achievement_id",))]


async def prerequisities_met(player: Player, achievement: Achievement, prerequisities: list[Achievement]):
    if not prerequisities:
        return True

    completed_count = await UserAchievement.objects.filter(
        player=player, achievement_id__in=[x.pk for x in prerequisities], completed=True
    ).acount()

    if achievement.prerequisite_logic == PrerequisiteLogic.ALL:
        return completed_count == len(prerequisities)
    else:
        return completed_count > 0


async def progress_achievement(player: Player, achievement_type: AchievementType, **context):
    checker = CHECKERS.get(achievement_type)
    achievements = Achievement.objects.prefetch_related("prerequisities").filter(type=achievement_type)

    async for achievement in achievements:
        prerequisities = [x async for x in achievement.prerequisities.all()]
        if not await prerequisities_met(player, achievement, prerequisities):
            continue

        result = True
        if checker is not None:
            result = await checker(achievement, player, **context)

        if result is False:
            continue

        user_achievement, _ = await UserAchievement.objects.aget_or_create(
            player=player, achievement=achievement, defaults={"progress": 0}
        )

        if user_achievement.completed:
            continue

        if isinstance(result, bool):
            user_achievement.progress += 1
        elif isinstance(result, int):
            user_achievement.progress = min(result, achievement.target_value)
        else:
            raise TypeError(f"Excepted bool or int, not {type(result).__name__}")

        if user_achievement.progress >= achievement.target_value:
            user_achievement.progress = achievement.target_value
            user_achievement.completed = True
            user_achievement.completed_at = timezone.now()

            await player.add_money(achievement.currency_reward)
        # TODO: enviar mensaje/log

        await user_achievement.asave(update_fields=["progress", "completed", "completed_at"])
