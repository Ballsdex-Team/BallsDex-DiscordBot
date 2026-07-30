from django.db.models import Count

from bd_models.models import Ball, BallInstance, Player

from ..models import Achievement, AchievementType, register_checker


@register_checker(AchievementType.COMPLETION_PERCENTAGE)
async def check_completion_percentage(achievement: Achievement, player: Player, **kwargs):
    total_balls = await Ball.enabled_objects.acount()
    if total_balls == 0:
        return False

    full_sets = achievement.target_value // 100
    partial_percentage = achievement.target_value % 100

    owned_counts = [
        row["count"]
        async for row in (
            BallInstance.objects.filter(player=player, ball__enabled=True).values("ball_id").annotate(count=Count("id"))
        )
    ]

    progress = 0

    if full_sets:
        for count in owned_counts:
            progress += min(count, full_sets)

    if partial_percentage:
        extra_needed = full_sets + 1

        balls_with_extra = sum(1 for count in owned_counts if count >= extra_needed)

        progress += balls_with_extra * (partial_percentage / 100)

    percentage = (progress / total_balls) * 100

    return int(percentage)
