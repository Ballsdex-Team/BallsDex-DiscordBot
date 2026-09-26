"""
Makes the quests of an event pass progress, completes them and tells players what they can claim.

Quests only progress inside the bot process, once `engine.configure` was called, and only while their pass is
running: nothing done before the pass starts or after it ends is ever counted. The engine listens to
`ballsdex.core.game_events.bus`, like the achievement engine, so a package dispatching an action doesn't know or
care that event passes exist.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.utils import timezone

from ballsdex.core.game_events import Event, EventContext, normalize_command
from settings.models import settings

from .access import progress_gate
from .models import EventPass, Measure, PlayerPass, PlayerQuest, Quest, QuestType, Reset, Reward, Source
from .rewards import grant
from .state import REWARD_LINES, finished_tier_ids, period_of, unlocked_tier_ids
from .types import TYPES

if TYPE_CHECKING:
    from datetime import datetime

    from ballsdex.core.bot import BallsDexBot

    from .notifications import PassNotifier

__all__ = ("engine",)

log = logging.getLogger("eventpass")


@dataclass
class Increment:
    amount: int


@dataclass
class Absolute:
    value: int


@dataclass
class Completion:
    """
    A quest a player just finished, and what they got if it was given right away.
    """

    quest: Quest
    period: str
    auto_claimed: bool = False
    summary: str = ""


class EventPassEngine:
    CACHE_TTL = 60

    def __init__(self):
        self.bot: BallsDexBot | None = None
        self.notifier: PassNotifier | None = None
        self._quests: list[Quest] = []
        self._loaded_at = 0.0
        self._locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    def configure(self, bot: BallsDexBot | None, notifier: PassNotifier | None):
        self.bot = bot
        self.notifier = notifier
        self._loaded_at = 0.0

    # -- entry points ------------------------------------------------------------------------------------------------

    async def handle_event(self, player_id: int, event: Event, context: EventContext, channel_id: int | None):
        """
        Subscriber of the game event bus.
        """
        if self.bot is None:
            return
        now = timezone.now()
        candidates = [
            quest
            for quest in await self.active_quests()
            if quest.type in TYPES and event in TYPES[quest.type].events and self._in_window(quest, now)
        ]
        if not candidates:
            return
        try:
            async with self._locks[player_id]:
                completions = await self._process(player_id, candidates, context, event, channel_id, now)
        except Exception:
            log.exception("Failed to progress the quests of player %s for %s", player_id, event)
            return
        if completions and self.notifier:
            await self.notifier.add(player_id, completions, channel_id)

    async def listens_to_command(self, name: str) -> bool:
        return any(
            quest.type == QuestType.COMMAND and normalize_command(quest.command_name) == name
            for quest in await self.active_quests()
        )

    async def active_quests(self) -> list[Quest]:
        """
        Every quest of every active pass, cached for a minute so the bot doesn't query them on each action.
        """
        if time.monotonic() - self._loaded_at > self.CACHE_TTL:
            self._quests = [
                quest
                async for quest in Quest.objects.filter(enabled=True, event_pass__status=EventPass.Status.ACTIVE)
                .select_related("event_pass", "tier", "reward", "ball", "special", "group", "item", "merchant_item")
                .select_related("collector", "tier_level")
                .prefetch_related(REWARD_LINES)
            ]
            self._loaded_at = time.monotonic()
        return self._quests

    def invalidate(self):
        self._loaded_at = 0.0

    # -- processing --------------------------------------------------------------------------------------------------

    @staticmethod
    def _in_window(quest: Quest, now: datetime) -> bool:
        starts_at, ends_at = quest.window()
        return quest.event_pass.running(now) and starts_at <= now <= ends_at

    async def _process(
        self,
        player_id: int,
        candidates: list[Quest],
        context: EventContext,
        event: Event,
        channel_id: int | None,
        now: datetime,
    ) -> list[Completion]:
        # a locked tier holds its quests: they only start moving once the player unlocks it
        by_pass: dict[int, list[Quest]] = defaultdict(list)
        for quest in candidates:
            by_pass[quest.event_pass_id].append(quest)
        allowed: list[Quest] = []
        for quests in by_pass.values():
            event_pass = quests[0].event_pass
            # a pass reserved to a role or to newcomers only moves for the players taking part in it
            once_allowed, repeat_allowed = await progress_gate(player_id, event_pass)
            if not once_allowed and not repeat_allowed:
                continue
            if any(quest.tier_id for quest in quests):
                unlocked = await unlocked_tier_ids(player_id, event_pass, now)
            else:
                unlocked = set()
            allowed.extend(
                quest
                for quest in quests
                if (quest.tier_id is None or quest.tier_id in unlocked)
                and (repeat_allowed if quest.reset != Reset.NONE else once_allowed)
            )
        if not allowed:
            return []

        periods = {quest.pk: period_of(quest, now) for quest in allowed}
        rows = {
            (row.quest_id, row.period): row
            async for row in PlayerQuest.objects.filter(
                player_id=player_id, quest_id__in=[quest.pk for quest in allowed]
            )
        }

        completions: list[Completion] = []
        for quest in allowed:
            period = periods[quest.pk]
            row = rows.get((quest.pk, period))
            if row is not None and row.completed_at:
                continue
            if not self._matches(quest, context, event):
                continue
            result = self._evaluate(quest, context, event)
            if result is None:
                continue
            completion = await self._apply(quest, player_id, row, period, result, now, context, channel_id)
            if completion is not None:
                completions.append(completion)
        return completions

    def _matches(self, quest: Quest, context: EventContext, event: Event) -> bool:
        """
        The filters that apply to every type: where it happened, who with, and how much it moved.
        """
        event_pass = quest.event_pass
        if quest.main_server_only or event_pass.main_server_only:
            if event_pass.main_server_id is None or context.server_id != event_pass.main_server_id:
                return False
        if quest.partner_discord_id and context.partner_discord_id != quest.partner_discord_id:
            return False
        if quest.min_currency:
            moved = abs(context.amount) or abs(context.price) or context.received_currency
            if moved < quest.min_currency:
                return False
        definition = TYPES.get(quest.type)
        if definition and definition.filters_instances and context.instances:
            if not any(quest.matches_instance(instance) for instance in context.instances):
                return False
        return True

    def _evaluate(self, quest: Quest, context: EventContext, event: Event) -> Increment | Absolute | None:
        """
        How much this action moves the quest, `None` when it doesn't count at all.
        """
        match quest.type:
            case QuestType.CATCH | QuestType.OBTAIN | QuestType.AUCTION_CREATE | QuestType.GIVE_TREASURES:
                count = sum(1 for x in context.instances if quest.matches_instance(x) and self._fast_enough(quest, x))
                return Increment(count) if count else None

            case QuestType.SHOP_BUY | QuestType.SELL | QuestType.AUCTION_WON:
                if quest.measure == Measure.AMOUNT:
                    amount = abs(context.price or context.amount)
                    return Increment(amount) if amount else None
                count = sum(1 for x in context.instances if quest.matches_instance(x))
                return Increment(count or 1)

            case QuestType.CATCH_CURRENCY:
                if quest.measure == Measure.AMOUNT:
                    return Increment(abs(context.amount)) if context.amount else None
                return Increment(1)

            case QuestType.COMMAND:
                if normalize_command(context.command_name) != normalize_command(quest.command_name):
                    return None
                # only a command that said it did nothing is turned away; one that never reports still counts,
                # so this flag can be set without making a quest impossible to finish
                if quest.require_command_effect and context.command_worked is False:
                    return None
                return Increment(1)

            case QuestType.TRADE:
                needs_treasure = quest.must_receive_treasure or quest.ball_id or quest.special_id or quest.any_special
                if needs_treasure and not any(quest.matches_instance(x) for x in context.instances):
                    return None
                return Increment(1)

            case QuestType.TRADE_TREASURES:
                received = len(context.instances)
                # a trade where one side gives nothing is a gift, not an exchange
                if not (received or context.received_currency) or not (context.given_count or context.given_currency):
                    return None
                exchanged = received + context.given_count
                if not exchanged:
                    return None
                return Absolute(exchanged) if quest.in_one_trade else Increment(exchanged)

            case QuestType.FRIEND | QuestType.BATTLE_WIN:
                return Increment(1)

            case QuestType.GIVE_CURRENCY:
                amount = abs(context.amount)
                if not amount:
                    return None
                return Increment(amount if quest.measure == Measure.AMOUNT else 1)

            case QuestType.RECEIVE_CURRENCY:
                amount = context.received_currency or abs(context.amount)
                if not amount:
                    return None
                return Increment(amount if quest.measure == Measure.AMOUNT else 1)

            case QuestType.SPEND_CURRENCY:
                # the ledger event is signed, only what leaves the player counts
                if context.amount >= 0:
                    return None
                spent = abs(context.amount)
                return Increment(spent if quest.measure == Measure.AMOUNT else 1)

            case QuestType.CRAFT:
                if quest.collector_id and context.collector_id != quest.collector_id:
                    return None
                if quest.tier_level_id and context.tier_level_id != quest.tier_level_id:
                    return None
                return Increment(1)

            case QuestType.PACK_BUY:
                if quest.item_id and context.item_id != quest.item_id:
                    return None
                return self._purchase(quest, context)

            case QuestType.MERCHANT_BUY:
                if quest.merchant_item_id and context.merchant_item_id != quest.merchant_item_id:
                    return None
                return self._purchase(quest, context)

            case QuestType.AUCTION_BID:
                if quest.measure == Measure.AMOUNT:
                    return Increment(context.price) if context.price else None
                return Increment(1)
        return None

    @staticmethod
    def _purchase(quest: Quest, context: EventContext) -> Increment | None:
        if quest.measure == Measure.AMOUNT:
            spent = abs(context.price or context.amount)
            return Increment(spent) if spent else None
        return Increment(1)

    @staticmethod
    def _fast_enough(quest: Quest, instance) -> bool:
        if quest.max_catch_seconds is None:
            return True
        if not instance.catch_date or not instance.spawned_time:
            return False
        return (instance.catch_date - instance.spawned_time).total_seconds() <= quest.max_catch_seconds

    async def _apply(
        self,
        quest: Quest,
        player_id: int,
        row: PlayerQuest | None,
        period: str,
        result: Increment | Absolute,
        now: datetime,
        context: EventContext,
        channel_id: int | None,
    ) -> Completion | None:
        target = max(quest.target, 1)
        if row is None:
            row, _ = await PlayerQuest.objects.aget_or_create(player_id=player_id, quest_id=quest.pk, period=period)
            if row.completed_at:
                return None

        if isinstance(result, Increment):
            progress = min(row.progress + result.amount, target)
        else:
            progress = min(max(result.value, row.progress), target)

        if progress < target:
            if progress != row.progress:
                await PlayerQuest.objects.filter(pk=row.pk, completed_at__isnull=True).aupdate(progress=progress)
            return None

        # only the update that actually completes the quest counts, whichever action got there first
        updated = await PlayerQuest.objects.filter(pk=row.pk, completed_at__isnull=True).aupdate(
            progress=target, completed_at=now
        )
        if not updated:
            return None
        await PlayerPass.objects.aget_or_create(player_id=player_id, event_pass_id=quest.event_pass_id)
        log.debug("Player %s completed quest %s (%s)", player_id, quest.pk, period or "once")

        completion = Completion(quest=quest, period=period)
        # the quest may hand its reward over on its own, or the bot may be set to never ask for a click
        gives_now = not quest.claim_required or settings.pass_auto_claim
        if gives_now and quest.reward_id:
            given = await grant(
                player_id,
                quest.event_pass,
                quest.reward,
                source=Source.QUEST,
                source_id=quest.pk,
                period=period,
                server_id=context.server_id,
                channel_id=channel_id,
                label=quest.name,
            )
            if given is not None:
                await PlayerQuest.objects.filter(pk=row.pk).aupdate(claimed_at=now)
                completion.auto_claimed = True
                completion.summary = given.summary
        return completion

    # -- claiming ----------------------------------------------------------------------------------------------------

    async def claim(
        self, player_id: int, quest: Quest, *, channel_id: int | None = None, server_id: int | None = None
    ) -> tuple[str, str]:
        """
        Claim the reward of a completed quest.

        Returns
        -------
        tuple[str, str]
            A status (`claimed`, `already`, `not_completed`, `closed`, `nothing`) and what the player got.
        """
        now = timezone.now()
        if not quest.event_pass.claimable(now):
            return ("closed", "")
        period = period_of(quest, now)
        row = await PlayerQuest.objects.filter(player_id=player_id, quest_id=quest.pk, period=period).afirst()
        if row is None or row.completed_at is None:
            return ("not_completed", "")
        if row.claimed_at is not None:
            return ("already", "")
        if quest.reward_id is None:
            await PlayerQuest.objects.filter(pk=row.pk, claimed_at__isnull=True).aupdate(claimed_at=now)
            return ("nothing", "")

        given = await grant(
            player_id,
            quest.event_pass,
            quest.reward,
            source=Source.QUEST,
            source_id=quest.pk,
            period=period,
            server_id=server_id,
            channel_id=channel_id,
            label=quest.name,
        )
        if given is None:
            await PlayerQuest.objects.filter(pk=row.pk, claimed_at__isnull=True).aupdate(claimed_at=now)
            return ("already", "")
        await PlayerQuest.objects.filter(pk=row.pk).aupdate(claimed_at=now)
        return ("claimed", given.summary)

    async def claim_tier(
        self, player_id: int, tier, *, channel_id: int | None = None, server_id: int | None = None
    ) -> tuple[str, str]:
        """
        Claim the reward of a finished tier, if it has one.
        """
        event_pass = tier.event_pass
        if not event_pass.claimable():
            return ("closed", "")
        if tier.reward_id is None:
            return ("nothing", "")
        if tier.pk not in await finished_tier_ids(player_id, event_pass):
            return ("unfinished", "")
        given = await grant(
            player_id,
            event_pass,
            tier.reward,
            source=Source.TIER,
            source_id=tier.pk,
            server_id=server_id,
            channel_id=channel_id,
            label=tier.name,
        )
        return ("already", "") if given is None else ("claimed", given.summary)

    async def claim_final(
        self, player_id: int, event_pass: EventPass, *, channel_id: int | None = None, server_id: int | None = None
    ) -> tuple[str, str]:
        """
        Claim the reward given for finishing the whole pass.
        """
        if not event_pass.claimable():
            return ("closed", "")
        if event_pass.final_reward_id is None:
            return ("nothing", "")
        tiers = {tier async for tier in event_pass.tiers.values_list("pk", flat=True)}
        if tiers and not tiers <= await finished_tier_ids(player_id, event_pass):
            return ("unfinished", "")
        # loaded here: the pass comes from queries that don't join its reward, and reading `event_pass.final_reward`
        # would be a synchronous query, which async code is not allowed to make
        final_reward = await Reward.objects.filter(pk=event_pass.final_reward_id).afirst()
        if final_reward is None:
            return ("nothing", "")
        given = await grant(
            player_id,
            event_pass,
            final_reward,
            source=Source.FINAL,
            source_id=event_pass.pk,
            server_id=server_id,
            channel_id=channel_id,
            label=event_pass.name,
        )
        if given is None:
            return ("already", "")
        await PlayerPass.objects.aupdate_or_create(
            player_id=player_id, event_pass_id=event_pass.pk, defaults={"final_claimed_at": timezone.now()}
        )
        return ("claimed", given.summary)


engine = EventPassEngine()
