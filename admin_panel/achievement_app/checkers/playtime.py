from django.utils import timezone

from bd_models.models import BallInstance, Player

from ..models import Achievement, AchievementType, register_checker

DAYS_PER_UNIT = {"days": 1, "months": 30, "years": 365}


@register_checker(AchievementType.PLAYTIME)
async def check_playtime(achievement: Achievement, player: Player, **kwargs):
    instance = await BallInstance.objects.filter(player=player).order_by("catch_date").afirst()
    if not instance:
        return False

    unit = achievement.extra_params.get("unit", "months")
    days_per_unit = DAYS_PER_UNIT.get(unit, 30)

    elapsed_days = (timezone.now() - instance.catch_date).days
    elapsed_units = elapsed_days // days_per_unit

    return elapsed_units
