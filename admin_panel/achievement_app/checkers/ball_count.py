from bd_models.models import BallInstance, Player

from ..models import Achievement, AchievementType, register_checker


@register_checker(AchievementType.BALL_COUNT)
async def check_ball_count(achievement: Achievement, player: Player, **kwargs):
    qs = BallInstance.objects.filter(player=player)

    if achievement.cached_ball:
        qs = qs.filter(ball=achievement.cached_ball)
    if achievement.cached_special:
        qs = qs.filter(special=achievement.cached_special)

    return await qs.acount()
