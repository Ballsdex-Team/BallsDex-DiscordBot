from bd_models.models import Player

from ..models import Achievement, AchievementType, register_checker


@register_checker(AchievementType.FASTEST_CATCHER)
async def check_catch_time(achievement: Achievement, player: Player, **kwargs):
    elapsed_seconds = kwargs.get("elapsed_seconds", 0)

    if achievement.required_value is None:
        return False

    if elapsed_seconds <= achievement.required_value:
        return True

    return False
