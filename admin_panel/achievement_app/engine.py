"""
Makes achievements progress when players do something, unlocks them and notifies players.

Achievements only progress from the bot process, once `engine.configure` was called. Actions made from the admin
panel or management commands never unlock anything.

The engine doesn't listen to the game itself: it subscribes to `ballsdex.core.game_events.bus`, which is where
every package dispatches what players do. Packages telling the game something happened talk to the bus, never to
this engine.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from currency_app.ledger import aadjust_money
from currency_app.models import BerryTransaction
from django.db.models import Count, Q
from django.db.models.expressions import RawSQL
from django.utils import timezone

from ballsdex.core.game_events import Event, EventContext
from ballsdex.core.utils.background import run_on_bot_loop
from bd_models.models import BallInstance, Friendship, Player, balls, groups

from .models import (
    DAYS_PER_UNIT,
    Achievement,
    AchievementType,
    PlayerAchievementStats,
    PrerequisiteLogic,
    UserAchievement,
    normalize_command,
)
from .types import TYPES

if TYPE_CHECKING:
    from datetime import datetime

    from django.db.models import QuerySet

    from ballsdex.core.bot import BallsDexBot

    from .notifications import AchievementNotifier

__all__ = ("Event", "EventContext", "engine")

log = logging.getLogger(__name__)


@dataclass
class Increment:
    amount: int


@dataclass
class Absolute:
    value: int


class AchievementEngine:
    CACHE_TTL = 60

    def __init__(self):
        self.bot: BallsDexBot | None = None
        self.notifier: AchievementNotifier | None = None
        self._achievements: list[Achievement] = []
        self._prerequisites: dict[int, set[int]] = {}
        self._loaded_at = 0.0
        self._locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    def configure(self, bot: BallsDexBot | None, notifier: AchievementNotifier | None):
        self.bot = bot
        self.notifier = notifier
        self._loaded_at = 0.0

    # -- entry points ------------------------------------------------------------------------------------------------

    async def dispatch(
        self, player: Player | int, event: Event, *, context: EventContext | None = None, channel_id: int | None = None
    ) -> list[Achievement]:
        """
        Make the achievements listening to this event progress for a player, and notify them of what they unlocked.

        Parameters
        ----------
        player: Player | int
            The player (or its primary key) who did something.
        event: Event
            What the player did.
        context: EventContext | None
            Details about the action, like the treasures involved.
        channel_id: int | None
            Where the action happened, to notify the player there.
        """
        if self.bot is None:
            return []
        player_id = player if isinstance(player, int) else player.pk
        try:
            async with self._locks[player_id]:
                unlocked = await self._process(player_id, event, context or EventContext())
        except Exception:
            log.exception("Failed to process achievements of player %s for %s", player_id, event)
            return []
        if unlocked and self.notifier:
            await self.notifier.add(player_id, unlocked, channel_id)
        return unlocked

    async def sync_player(self, player: Player | int) -> list[Achievement]:
        """
        Refresh the progress of a player on every achievement based on what they own or have (treasures, groups,
        completion, friends, favorites, playtime), and unlock the ones they deserve.

        Achievements counting actions (catches, trades, battles) can't be refreshed, those are only counted when the
        action happens.
        """
        if self.bot is None:
            return []
        player_id = player if isinstance(player, int) else player.pk
        async with self._locks[player_id]:
            return await self._process(player_id, Event.SYNC, EventContext())

    def dispatch_soon(
        self, player_id: int, event: Event, *, context: EventContext | None = None, channel_id: int | None = None
    ):
        """
        Thread-safe version of `dispatch` that doesn't wait for the result.
        """
        if self.bot is None:
            return
        run_on_bot_loop(lambda: self.dispatch(player_id, event, context=context, channel_id=channel_id))

    async def handle_event(self, player_id: int, event: Event, context: EventContext, channel_id: int | None):
        """
        Subscriber of `ballsdex.core.game_events.bus`, which is how every action reaches the engine.
        """
        await self.dispatch(player_id, event, context=context, channel_id=channel_id)

    async def listens_to_command(self, name: str) -> bool:
        """
        Whether an active achievement counts the uses of this command. Asked by the bus before it dispatches one.
        """
        return any(
            achievement.type == AchievementType.COMMAND and normalize_command(achievement.command_name) == name
            for achievement in await self.active_achievements()
        )

    # -- processing --------------------------------------------------------------------------------------------------

    async def active_achievements(self) -> list[Achievement]:
        if time.monotonic() - self._loaded_at > self.CACHE_TTL:
            achievements = [
                achievement
                async for achievement in Achievement.objects.filter(status=Achievement.Status.ACTIVE)
                .select_related("ball", "special", "group", "category")
                .prefetch_related("prerequisities")
            ]
            self._prerequisites = {a.pk: {p.pk for p in a.prerequisities.all()} for a in achievements}
            self._achievements = achievements
            self._loaded_at = time.monotonic()
        return self._achievements

    async def _process(self, player_id: int, event: Event, context: EventContext) -> list[Achievement]:
        if event == Event.CATCH:
            await self._remember_first_catch(player_id, context)

        candidates = [a for a in await self.active_achievements() if event in TYPES[a.type].events]
        if not candidates:
            return []

        user_achievements = {
            ua.achievement_id: ua
            async for ua in UserAchievement.objects.filter(
                player_id=player_id, achievement_id__in=[a.pk for a in candidates]
            )
        }
        completed = {achievement_id for achievement_id, ua in user_achievements.items() if ua.completed}
        prerequisite_ids = set().union(*(self._prerequisites.get(a.pk, set()) for a in candidates))
        if unknown := prerequisite_ids - user_achievements.keys():
            completed.update(
                [
                    achievement_id
                    async for achievement_id in UserAchievement.objects.filter(
                        player_id=player_id, achievement_id__in=unknown, completed=True
                    ).values_list("achievement_id", flat=True)
                ]
            )

        now = timezone.now()
        unlocked: list[Achievement] = []
        pending = [achievement for achievement in candidates if achievement.pk not in completed]
        # an achievement unlocked now may be the prerequisite of another one, which is then checked again
        while pending:
            waiting: list[Achievement] = []
            for achievement in pending:
                if not self._prerequisites_met(achievement, completed):
                    waiting.append(achievement)
                    continue
                result = await self._evaluate(achievement, player_id, context, event)
                if result is None:
                    continue
                if await self._apply(achievement, player_id, user_achievements.get(achievement.pk), result, now):
                    unlocked.append(achievement)
                    completed.add(achievement.pk)
            if len(waiting) == len(pending) or not unlocked:
                break
            pending = waiting
        return unlocked

    def _prerequisites_met(self, achievement: Achievement, completed: set[int]) -> bool:
        prerequisites = self._prerequisites.get(achievement.pk)
        if not prerequisites:
            return True
        if achievement.prerequisite_logic == PrerequisiteLogic.ANY:
            return bool(prerequisites & completed)
        return prerequisites <= completed

    def target(self, achievement: Achievement) -> int:
        if achievement.type == AchievementType.COMPLETE_GROUP and not achievement.target_value:
            group = groups.get(achievement.group_id) if achievement.group_id else None
            return max(len(group._ball_ids) if group else 1, 1)
        return max(achievement.target_value, 1)

    async def _apply(
        self,
        achievement: Achievement,
        player_id: int,
        user_achievement: UserAchievement | None,
        result: Increment | Absolute,
        now: datetime,
    ) -> bool:
        target = self.target(achievement)
        if user_achievement is None:
            user_achievement, _ = await UserAchievement.objects.aget_or_create(
                player_id=player_id, achievement_id=achievement.pk
            )
            if user_achievement.completed:
                return False

        if isinstance(result, Increment):
            progress = min(user_achievement.progress + result.amount, target)
        else:
            progress = min(result.value, target)

        if progress < target:
            if progress != user_achievement.progress:
                user_achievement.progress = progress
                await UserAchievement.objects.filter(pk=user_achievement.pk, completed=False).aupdate(progress=progress)
            return False

        # only the update that actually completes the achievement gives the reward
        updated = await UserAchievement.objects.filter(pk=user_achievement.pk, completed=False).aupdate(
            progress=target, completed=True, completed_at=now
        )
        if not updated:
            return False
        user_achievement.progress, user_achievement.completed, user_achievement.completed_at = target, True, now
        if achievement.currency_reward:
            await aadjust_money(
                player_id,
                achievement.currency_reward,
                reason=BerryTransaction.Reason.ACHIEVEMENT,
                description=f"Unlocked {achievement.name}",
            )
        log.debug("Player %s unlocked achievement %s", player_id, achievement.pk)
        return True

    async def _remember_first_catch(self, player_id: int, context: EventContext):
        dates = [instance.catch_date for instance in context.instances if instance.catch_date]
        if not dates:
            return
        stats, created = await PlayerAchievementStats.objects.aget_or_create(
            player_id=player_id, defaults={"first_catch_at": min(dates)}
        )
        if not created and stats.first_catch_at is None:
            stats.first_catch_at = min(dates)
            await stats.asave(update_fields=("first_catch_at",))

    # -- evaluation of each type -------------------------------------------------------------------------------------

    async def _evaluate(
        self, achievement: Achievement, player_id: int, context: EventContext, event: Event
    ) -> Increment | Absolute | None:
        # a sync has no treasure to look at, achievements based on a state are all checked
        refresh = event == Event.SYNC
        match achievement.type:
            case AchievementType.CATCH:
                count = sum(
                    1
                    for x in context.instances
                    if achievement.matches_instance(x) and self._fast_enough(achievement, x)
                )
                return Increment(count) if count else None

            case AchievementType.OBTAIN:
                count = sum(1 for x in context.instances if achievement.matches_instance(x))
                return Increment(count) if count else None

            case AchievementType.OWN:
                if not refresh and not any(achievement.matches_instance(x) for x in context.instances):
                    return None
                return Absolute(await owned_queryset(achievement, player_id).acount())

            case AchievementType.COMPLETE_GROUP:
                group = groups.get(achievement.group_id) if achievement.group_id else None
                if group is None:
                    return None
                if not refresh and not any(x.ball_id in group._ball_ids for x in context.instances):
                    return None
                owned = (
                    BallInstance.objects.filter(player_id=player_id, ball_id__in=group._ball_ids)
                    .values("ball_id")
                    .distinct()
                )
                return Absolute(await owned.acount())

            case AchievementType.COMPLETION:
                if not refresh and not any((ball := balls.get(x.ball_id)) and ball.enabled for x in context.instances):
                    return None
                return Absolute(await completion_percentage(player_id, achievement.target_value))

            case AchievementType.TRADE:
                if achievement.partner_discord_id and context.partner_discord_id != achievement.partner_discord_id:
                    return None
                if achievement.min_currency and context.received_currency < achievement.min_currency:
                    return None
                needs_treasure = (
                    achievement.must_receive_treasure
                    or achievement.ball_id
                    or achievement.special_id
                    or achievement.any_special
                )
                if needs_treasure and not any(achievement.matches_instance(x) for x in context.instances):
                    return None
                return Increment(1)

            case AchievementType.TRADE_TREASURES:
                received = len(context.instances)
                # a trade where one side gives nothing is a gift, not an exchange
                if not (received or context.received_currency) or not (context.given_count or context.given_currency):
                    return None
                exchanged = received + context.given_count
                if not exchanged:
                    return None
                if achievement.in_one_trade:
                    return Absolute(exchanged) if exchanged >= achievement.target_value else None
                return Increment(exchanged)

            case AchievementType.FRIENDS:
                friends = Friendship.objects.filter(Q(player1_id=player_id) | Q(player2_id=player_id))
                return Absolute(await friends.acount())

            case AchievementType.FAVORITES:
                return Absolute(await BallInstance.objects.filter(player_id=player_id, favorite=True).acount())

            case AchievementType.BATTLE_WIN:
                return Increment(1)

            case AchievementType.COMMAND:
                if normalize_command(context.command_name) != normalize_command(achievement.command_name):
                    return None
                return Increment(1)

            case AchievementType.RECEIVE_CURRENCY:
                if achievement.partner_discord_id and context.partner_discord_id != achievement.partner_discord_id:
                    return None
                if achievement.min_currency and context.received_currency < achievement.min_currency:
                    return None
                return Increment(1)

            case AchievementType.PLAYTIME:
                first_catch = (
                    await PlayerAchievementStats.objects.filter(player_id=player_id)
                    .values_list("first_catch_at", flat=True)
                    .afirst()
                )
                if first_catch is None:
                    return None
                days = (timezone.now() - first_catch).days
                return Absolute(days // DAYS_PER_UNIT[achievement.time_unit])
        return None

    @staticmethod
    def _fast_enough(achievement: Achievement, instance: BallInstance) -> bool:
        if achievement.max_catch_seconds is None:
            return True
        if not instance.catch_date or not instance.spawned_time:
            return False
        return (instance.catch_date - instance.spawned_time).total_seconds() <= achievement.max_catch_seconds


def owned_queryset(achievement: Achievement, player_id: int) -> QuerySet[BallInstance]:
    """
    The treasures of a player passing the treasure filters of an achievement.
    """
    queryset = BallInstance.objects.filter(player_id=player_id)
    if achievement.ball_id:
        queryset = queryset.filter(ball_id=achievement.ball_id)
    if achievement.special_id:
        queryset = queryset.filter(special_id=achievement.special_id)
    elif achievement.any_special:
        queryset = queryset.filter(special_id__isnull=False)
    if achievement.group_id:
        group = groups.get(achievement.group_id)
        queryset = queryset.filter(ball_id__in=group._ball_ids if group else [])
    if achievement.server_id:
        queryset = queryset.filter(server_id=achievement.server_id)
    if achievement.min_attack_bonus is not None:
        queryset = queryset.filter(attack_bonus__gte=achievement.min_attack_bonus)
    if achievement.min_health_bonus is not None:
        queryset = queryset.filter(health_bonus__gte=achievement.min_health_bonus)
    if achievement.hex_contains:
        queryset = queryset.annotate(hex_id=RawSQL("to_hex(ballinstance.id)", ())).filter(
            hex_id__icontains=achievement.hex_contains
        )
    return queryset


async def completion_percentage(player_id: int, target: int) -> int:
    """
    Completion of a player in percent. Above 100%, 200% means owning two of each enabled treasure.
    """
    total = sum(1 for ball in balls.values() if ball.enabled)
    if total == 0:
        return 0
    owned = BallInstance.objects.filter(player_id=player_id, ball__enabled=True)
    if target <= 100:
        return await owned.values("ball_id").distinct().acount() * 100 // total

    full_sets, partial = divmod(target, 100)
    counts = [row["count"] async for row in owned.values("ball_id").annotate(count=Count("id"))]
    progress = sum(min(count, full_sets) for count in counts)
    if partial:
        progress += sum(1 for count in counts if count > full_sets) * partial / 100
    return int(progress * 100 / total)


engine = AchievementEngine()
