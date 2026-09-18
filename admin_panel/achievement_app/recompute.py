"""
Retroactive progress: gives players the progress they already have on achievements based on what they own, for
instance when a new collection achievement is created. Achievements counting actions (catches, trades...) can't be
recomputed, the history of those actions isn't kept, except the treasures exchanged: the trade history has them.
"""

from django.db import connection, transaction
from django.db.models import Count, Q
from django.utils import timezone

from bd_models.models import Ball, BallInstance, Friendship

from .models import DAYS_PER_UNIT, Achievement, AchievementType, PlayerAchievementStats, UserAchievement

RECOMPUTABLE_TYPES = {
    AchievementType.OWN,
    AchievementType.COMPLETE_GROUP,
    AchievementType.COMPLETION,
    AchievementType.FRIENDS,
    AchievementType.FAVORITES,
    AchievementType.PLAYTIME,
    AchievementType.TRADE_TREASURES,
}

# every trade where both sides gave something (treasures or currency), with the treasures it exchanged: the other
# trades are gifts, which also leave a trade behind
EXCHANGES_SQL = """
SELECT t.player1_id, t.player2_id, COUNT(o.id)
FROM trade t
JOIN tradeobject o ON o.trade_id = t.id
GROUP BY t.id
HAVING (COUNT(o.id) FILTER (WHERE o.player_id = t.player1_id) > 0 OR t.player1_money > 0)
   AND (COUNT(o.id) FILTER (WHERE o.player_id = t.player2_id) > 0 OR t.player2_money > 0)
"""


def _progress_by_player(achievement: Achievement) -> tuple[dict[int, int], int]:
    """
    Returns the progress of every player with some progress, and the target.
    """
    target = max(achievement.target_value, 1)
    match achievement.type:
        case AchievementType.OWN:
            queryset = BallInstance.objects.all()
            if achievement.ball_id:
                queryset = queryset.filter(ball_id=achievement.ball_id)
            if achievement.special_id:
                queryset = queryset.filter(special_id=achievement.special_id)
            elif achievement.any_special:
                queryset = queryset.filter(special_id__isnull=False)
            if achievement.group_id:
                queryset = queryset.filter(ball__groups=achievement.group_id)
            if achievement.min_attack_bonus is not None:
                queryset = queryset.filter(attack_bonus__gte=achievement.min_attack_bonus)
            if achievement.min_health_bonus is not None:
                queryset = queryset.filter(health_bonus__gte=achievement.min_health_bonus)
            rows = queryset.values("player_id").annotate(progress=Count("id"))
            return {row["player_id"]: row["progress"] for row in rows}, target

        case AchievementType.COMPLETE_GROUP:
            if not achievement.group_id:
                return {}, target
            ball_ids = list(Ball.objects.filter(groups=achievement.group_id).values_list("pk", flat=True))
            target = achievement.target_value or max(len(ball_ids), 1)
            rows = (
                BallInstance.objects.filter(ball_id__in=ball_ids)
                .values("player_id")
                .annotate(progress=Count("ball_id", distinct=True))
            )
            return {row["player_id"]: row["progress"] for row in rows}, target

        case AchievementType.COMPLETION:
            total = Ball.objects.filter(enabled=True).count()
            if not total:
                return {}, target
            if achievement.target_value <= 100:
                rows = (
                    BallInstance.objects.filter(ball__enabled=True)
                    .values("player_id")
                    .annotate(owned=Count("ball_id", distinct=True))
                )
                return {row["player_id"]: row["owned"] * 100 // total for row in rows}, target
            full_sets, partial = divmod(achievement.target_value, 100)
            progress: dict[int, float] = {}
            rows = (
                BallInstance.objects.filter(ball__enabled=True).values("player_id", "ball_id").annotate(n=Count("id"))
            )
            for row in rows:
                value = min(row["n"], full_sets) + (partial / 100 if partial and row["n"] > full_sets else 0)
                progress[row["player_id"]] = progress.get(row["player_id"], 0) + value
            return {player_id: int(value * 100 / total) for player_id, value in progress.items()}, target

        case AchievementType.FRIENDS:
            progress = {}
            for field in ("player1_id", "player2_id"):
                for row in Friendship.objects.values(field).annotate(n=Count("id")):
                    progress[row[field]] = progress.get(row[field], 0) + row["n"]
            return {player_id: int(value) for player_id, value in progress.items()}, target

        case AchievementType.FAVORITES:
            rows = BallInstance.objects.filter(favorite=True).values("player_id").annotate(progress=Count("id"))
            return {row["player_id"]: row["progress"] for row in rows}, target

        case AchievementType.TRADE_TREASURES:
            progress = {}
            with connection.cursor() as cursor:
                cursor.execute(EXCHANGES_SQL)
                for player1_id, player2_id, exchanged in cursor.fetchall():
                    for player_id in (player1_id, player2_id):
                        if achievement.in_one_trade:
                            progress[player_id] = max(progress.get(player_id, 0), exchanged)
                        else:
                            progress[player_id] = progress.get(player_id, 0) + exchanged
            return {player_id: int(value) for player_id, value in progress.items()}, target

        case AchievementType.PLAYTIME:
            now = timezone.now()
            days_per_unit = DAYS_PER_UNIT[achievement.time_unit]
            return {
                player_id: (now - first_catch).days // days_per_unit
                for player_id, first_catch in PlayerAchievementStats.objects.filter(
                    first_catch_at__isnull=False
                ).values_list("player_id", "first_catch_at")
            }, target
    return {}, target


def recompute_progress(achievement: Achievement, *, give_rewards: bool) -> tuple[int, int]:
    """
    Update the progress of every player on this achievement, and unlock it for those who reached the goal.

    Returns
    -------
    tuple[int, int]
        How many players had their progress updated, and how many unlocked the achievement.
    """
    # imported here, the ledger module imports bd_models
    from currency_app.ledger import adjust_money
    from currency_app.models import BerryTransaction

    if achievement.type not in RECOMPUTABLE_TYPES:
        raise ValueError(f"Achievements of type {achievement.type} can't be recomputed.")

    progress_by_player, target = _progress_by_player(achievement)
    now = timezone.now()
    updated = unlocked = 0
    with transaction.atomic():
        existing = {
            ua.player_id: ua
            for ua in UserAchievement.objects.select_for_update().filter(
                Q(player_id__in=progress_by_player.keys()), achievement=achievement
            )
        }
        to_create, to_update, rewarded = [], [], []
        for player_id, progress in progress_by_player.items():
            progress = min(progress, target)
            ua = existing.get(player_id)
            if ua is not None and (ua.completed or ua.progress == progress):
                continue
            if ua is None:
                if progress <= 0:
                    continue
                ua = UserAchievement(player_id=player_id, achievement=achievement)
                to_create.append(ua)
            else:
                to_update.append(ua)
            ua.progress = progress
            if progress >= target:
                ua.completed, ua.completed_at = True, now
                rewarded.append(player_id)
        UserAchievement.objects.bulk_create(to_create, batch_size=1000)
        UserAchievement.objects.bulk_update(to_update, ("progress", "completed", "completed_at"), batch_size=1000)
        updated, unlocked = len(to_create) + len(to_update), len(rewarded)

        if give_rewards and achievement.currency_reward:
            for player_id in rewarded:
                adjust_money(
                    player_id,
                    achievement.currency_reward,
                    reason=BerryTransaction.Reason.ACHIEVEMENT,
                    description=f"Unlocked {achievement.name} (retroactive)",
                )
    return updated, unlocked
