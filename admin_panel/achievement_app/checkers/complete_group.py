from bd_models.models import BallInstance, Player

from ..models import Achievement, AchievementType, register_checker


@register_checker(AchievementType.COMPLETE_GROUP)
async def check_complete_group(achievement: Achievement, player: Player, **kwargs):
    group = achievement.cached_group
    if group is None:
        return False

    required_ball_ids = {ball.pk async for ball in group.countryballs.all()}
    if not required_ball_ids:
        return False

    owned_count = (
        await BallInstance.objects.filter(player=player, ball_id__in=required_ball_ids)
        .values_list("ball_id", flat=True)
        .distinct()
        .acount()
    )

    return owned_count
