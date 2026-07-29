from bd_models.models import Player

from ..models import Achievement, AchievementType, register_checker


@register_checker(AchievementType.RECEIVE_BALL)
async def check_receive_ball(achievement: Achievement, player: Player, **kwargs):
    params = achievement.extra_params
    required_user_id = params.get("user_id")
    user_id = kwargs.get("user_id")

    if required_user_id:
        if not user_id:
            return False

        if str(user_id) != str(required_user_id):
            return False

    return True
