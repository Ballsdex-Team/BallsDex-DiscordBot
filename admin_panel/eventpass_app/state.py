"""
What a pass looks like for one player: which tiers are unlocked, how far each quest is, what can be claimed.

The engine uses it to know whether a quest is allowed to progress, and the /pass command uses the very same code
to draw the pass, so players can never see a tier the engine treats differently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from django.db.models import Prefetch
from django.utils import timezone

from bd_models.models import BallInstance, Player
from settings.utils import format_currency

from .models import EventPass, PassTier, PlayerQuest, Quest, RequirementKind, Reset, RewardLine, TierRequirement
from .types import player_description

# every treasure a reward or a requirement points at is loaded up front: reading `quest.ball` or `line.special`
# lazily would be a synchronous query, which async code is not allowed to make
REWARD_LINES = Prefetch("reward__lines", queryset=RewardLine.objects.select_related("ball", "special"))
TIER_REQUIREMENTS = Prefetch(
    "requirements", queryset=TierRequirement.objects.select_related("ball", "special").prefetch_related("quests")
)

if TYPE_CHECKING:
    from collections.abc import Iterable


def period_of(quest: Quest, now: datetime | None = None) -> str:
    """
    The period a quest is currently in: empty for a one-off quest, a day or a week for a repeating one. Periods
    follow the timezone of the admin panel (`TIME_ZONE`), not the player's.
    """
    if quest.reset == Reset.NONE:
        return ""
    local = timezone.localtime(now or timezone.now())
    if quest.reset == Reset.DAILY:
        return local.strftime("%Y-%m-%d")
    iso = local.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


@dataclass
class QuestState:
    quest: Quest
    period: str
    progress: int = 0
    completed_at: datetime | None = None
    claimed_at: datetime | None = None

    @property
    def target(self) -> int:
        return max(self.quest.target, 1)

    @property
    def completed(self) -> bool:
        return self.completed_at is not None

    @property
    def claimable(self) -> bool:
        return self.completed and self.claimed_at is None and self.quest.reward_id is not None

    @property
    def ratio(self) -> float:
        return min(self.progress / self.target, 1.0)

    @property
    def description(self) -> str:
        return player_description(self.quest)


@dataclass
class TierState:
    tier: PassTier
    unlocked: bool = False
    missing: list[str] = field(default_factory=list)
    quests: list[QuestState] = field(default_factory=list)
    reward_claimed: bool = False

    @property
    def completed(self) -> bool:
        return self.unlocked and bool(self.quests) and all(state.completed for state in self.quests)


@dataclass
class PassState:
    event_pass: EventPass
    tiers: list[TierState] = field(default_factory=list)
    loose_quests: list[QuestState] = field(default_factory=list)
    final_claimed: bool = False

    @property
    def quest_states(self) -> list[QuestState]:
        return self.loose_quests + [state for tier in self.tiers for state in tier.quests]

    @property
    def completed_count(self) -> int:
        return sum(1 for state in self.quest_states if state.completed)

    @property
    def claimable_count(self) -> int:
        return sum(1 for state in self.quest_states if state.claimable)

    @property
    def total_count(self) -> int:
        return len(self.quest_states)

    @property
    def all_tiers_unlocked(self) -> bool:
        return bool(self.tiers) and all(tier.unlocked for tier in self.tiers)


def describe_requirement(requirement: TierRequirement) -> str:
    """
    A requirement as players read it.
    """
    match requirement.kind:
        case RequirementKind.QUESTS_ALL:
            names = [quest.name for quest in requirement.quests.all()]
            return f"Complete {', '.join(names)}" if names else "Complete the quests above"
        case RequirementKind.QUESTS_COUNT:
            return f"Complete {requirement.count} quests of this pass"
        case RequirementKind.PREVIOUS_TIER:
            return "Unlock the previous tier"
        case RequirementKind.OWN_TREASURES:
            ball = requirement.cached_ball
            special = requirement.cached_special
            name = " ".join(x for x in ((special.name if special else ""), (ball.country if ball else "")) if x)
            return f"Own {requirement.count} {name or 'treasures'}"
        case RequirementKind.CURRENCY:
            return f"Have {format_currency(requirement.count, False)}"
        case RequirementKind.DATE:
            return f"Wait until <t:{int(requirement.date.timestamp())}:D>" if requirement.date else "Wait"
    return ""


async def _own_count(player_id: int, requirement: TierRequirement) -> int:
    queryset = BallInstance.objects.filter(player_id=player_id, deleted=False)
    if requirement.ball_id:
        queryset = queryset.filter(ball_id=requirement.ball_id)
    if requirement.special_id:
        queryset = queryset.filter(special_id=requirement.special_id)
    return await queryset.acount()


async def _requirement_met(
    requirement: TierRequirement,
    player_id: int,
    completed_quest_ids: set[int],
    unlocked_tier_ids: set[int],
    previous_tier: PassTier | None,
    now: datetime,
    money: int,
) -> bool:
    match requirement.kind:
        case RequirementKind.QUESTS_ALL:
            required = {quest.pk async for quest in requirement.quests.all()}
            return bool(required) and required <= completed_quest_ids
        case RequirementKind.QUESTS_COUNT:
            return len(completed_quest_ids) >= requirement.count
        case RequirementKind.PREVIOUS_TIER:
            return previous_tier is None or previous_tier.pk in unlocked_tier_ids
        case RequirementKind.OWN_TREASURES:
            return await _own_count(player_id, requirement) >= requirement.count
        case RequirementKind.CURRENCY:
            return money >= requirement.count
        case RequirementKind.DATE:
            return requirement.date is not None and now >= requirement.date
    return False


async def build_state(
    player: Player | None, event_pass: EventPass, *, quests: Iterable[Quest] | None = None, now: datetime | None = None
) -> PassState:
    """
    The whole pass as it stands for a player, tiers in order. Pass `None` for a player who has no account yet:
    everything is shown locked and empty.
    """
    now = now or timezone.now()
    state = PassState(event_pass=event_pass)
    if quests is None:
        quests = [
            quest
            # event_pass and reward are needed by the claim path, which runs in async code and can't lazy load
            async for quest in Quest.objects.filter(event_pass=event_pass, enabled=True)
            .select_related("event_pass", "tier", "reward", "ball", "special", "group", "item", "merchant_item")
            .select_related("collector", "tier_level")
            .prefetch_related(REWARD_LINES)
        ]
    quests = list(quests)
    tiers = [
        tier
        async for tier in PassTier.objects.filter(event_pass=event_pass)
        .select_related("event_pass", "reward")
        .prefetch_related(TIER_REQUIREMENTS, REWARD_LINES)
    ]

    progress: dict[tuple[int, str], PlayerQuest] = {}
    completed_quest_ids: set[int] = set()
    money = 0
    if player is not None:
        money = player.money
        async for row in PlayerQuest.objects.filter(player=player, quest__event_pass=event_pass):
            progress[(row.quest_id, row.period)] = row
            if row.completed_at:
                completed_quest_ids.add(row.quest_id)
        state.final_claimed = await event_pass.players.filter(player=player, final_claimed_at__isnull=False).aexists()

    def quest_state(quest: Quest) -> QuestState:
        period = period_of(quest, now)
        row = progress.get((quest.pk, period))
        return QuestState(
            quest=quest,
            period=period,
            progress=row.progress if row else 0,
            completed_at=row.completed_at if row else None,
            claimed_at=row.claimed_at if row else None,
        )

    unlocked_tier_ids: set[int] = set()
    previous: PassTier | None = None
    for tier in tiers:
        tier_state = TierState(tier=tier)
        requirements = list(tier.requirements.all())
        results = [
            await _requirement_met(
                requirement, player.pk if player else 0, completed_quest_ids, unlocked_tier_ids, previous, now, money
            )
            if player is not None
            else False
            for requirement in requirements
        ]
        if not requirements:
            tier_state.unlocked = True
        elif tier.unlock_logic == "any":
            tier_state.unlocked = any(results)
        else:
            tier_state.unlocked = all(results)
        tier_state.missing = [
            describe_requirement(requirement) for requirement, met in zip(requirements, results, strict=True) if not met
        ]
        if tier_state.unlocked:
            unlocked_tier_ids.add(tier.pk)
        tier_state.quests = [quest_state(quest) for quest in quests if quest.tier_id == tier.pk]
        state.tiers.append(tier_state)
        previous = tier

    state.loose_quests = [quest_state(quest) for quest in quests if quest.tier_id is None]
    if player is not None:
        claimed_tiers = {
            source_id
            async for source_id in event_pass.grants.filter(player=player, source="tier").values_list(
                "source_id", flat=True
            )
        }
        for tier_state in state.tiers:
            tier_state.reward_claimed = tier_state.tier.pk in claimed_tiers
    return state


async def unlocked_tier_ids(player_id: int, event_pass: EventPass, now: datetime | None = None) -> set[int]:
    """
    The tiers a player has unlocked, which is what decides whether their quests can progress.
    """
    now = now or timezone.now()
    tiers = [tier async for tier in PassTier.objects.filter(event_pass=event_pass).prefetch_related(TIER_REQUIREMENTS)]
    if not tiers:
        return set()
    completed_quest_ids = {
        quest_id
        async for quest_id in PlayerQuest.objects.filter(
            player_id=player_id, quest__event_pass=event_pass, completed_at__isnull=False
        ).values_list("quest_id", flat=True)
    }
    money = await Player.objects.filter(pk=player_id).values_list("money", flat=True).afirst() or 0

    unlocked: set[int] = set()
    previous: PassTier | None = None
    for tier in tiers:
        requirements = list(tier.requirements.all())
        if not requirements:
            unlocked.add(tier.pk)
        else:
            results = [
                await _requirement_met(requirement, player_id, completed_quest_ids, unlocked, previous, now, money)
                for requirement in requirements
            ]
            if any(results) if tier.unlock_logic == "any" else all(results):
                unlocked.add(tier.pk)
        previous = tier
    return unlocked
