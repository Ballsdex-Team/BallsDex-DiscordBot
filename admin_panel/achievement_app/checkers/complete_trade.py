from bd_models.models import Player

from ..models import Achievement, AchievementType, register_checker


@register_checker(AchievementType.COMPLETE_TRADE)
async def check_complete_trade(achievement: Achievement, player: Player, **kwargs):
    params = achievement.extra_params
    requires_currency = params.get("requires_currency")
    received_coins = kwargs.get("received_coins", 0)

    if requires_currency:
        if received_coins <= achievement.required_value:
            return False

    return True
