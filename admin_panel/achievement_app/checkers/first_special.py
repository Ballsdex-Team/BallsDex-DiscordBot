from bd_models.models import Player

from ..models import Achievement, AchievementType, register_checker


@register_checker(AchievementType.FIRST_SPECIAL)
async def check_first_special(achievement: Achievement, player: Player, **kwargs):
    special = kwargs.get("special")
    if not special:
        return False

    if achievement.cached_special and achievement.cached_special.pk != special.pk:
        return False

    return True
