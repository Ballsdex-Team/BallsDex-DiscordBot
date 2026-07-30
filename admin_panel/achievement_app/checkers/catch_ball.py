from typing import TYPE_CHECKING

from bd_models.models import Player

from ..models import Achievement, AchievementType, register_checker

if TYPE_CHECKING:
    from bd_models.models import BallInstance


@register_checker(AchievementType.CATCH_BALL)
async def check_catch_ball(achievement: Achievement, player: Player, **kwargs):
    instance: "BallInstance | None" = kwargs.get("instance")
    if not instance:
        return False

    if achievement.cached_ball and instance.ball_id != achievement.cached_ball.pk:
        return False
    if achievement.cached_special and instance.special_id != achievement.cached_special.pk:
        return False

    params = achievement.extra_params
    if server_id := params.get("server_id"):
        if instance.server_id != int(server_id):
            return False

    if (attack_bonus := params.get("attack_bonus")) is not None:
        if instance.attack_bonus < attack_bonus:
            return False

    if (health_bonus := params.get("health_bonus")) is not None:
        if instance.health_bonus < health_bonus:
            return False

    if hex_contains := params.get("hex_contains"):
        if hex_contains not in f"{instance.pk:x}":
            return False
    return True
