from bd_models.models import Player

from ..models import Achievement, AchievementType, register_checker


@register_checker(AchievementType.CATCH_BALL)
async def check_catch_ball(achievement: Achievement, player: Player, **kwargs):
    ball = kwargs.get("ball_id")

    if (ball and achievement.ball_id) and achievement.ball_id != ball.pk:
        return False

    params = achievement.extra_params

    if server_id := params.get("server_id"):
        if kwargs.get("server_id") != int(server_id):
            return False

    return True
