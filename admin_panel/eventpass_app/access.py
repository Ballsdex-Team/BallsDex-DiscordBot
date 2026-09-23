"""
Who is allowed on a pass.

A pass with no `PassRequirement` is open to everyone, which is what every pass written before this was. A pass that
has some is only for the players meeting them, and the verdict is kept on their `PlayerPass` row rather than being
recomputed everywhere: a role can only be read from a Discord interaction, while the game event bus that moves
quests forward sees nothing but a player id.

That gives two moments:

- **Entering**, from `/pass view`, where the Discord member is at hand: every condition is checked, and a player who
  passes gets a `PlayerPass` row. Every later visit rechecks it and updates `eligible`.
- **Playing**, from the engine, with only the stored verdict and the conditions that can be counted from the
  database. A player who entered keeps the quests they can only do once — it would be unfair to take away something
  half finished — but the quests that come back every day or week stop as soon as they no longer qualify, otherwise
  someone could enter a beginners' pass and farm its weekly quests forever.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

from bd_models.models import BallInstance, Player

from .models import AccessKind, EventPass, Logic, PassRequirement, PlayerPass

if TYPE_CHECKING:
    from collections.abc import Iterable

    import discord


async def requirements_of(event_pass: EventPass) -> list[PassRequirement]:
    return [requirement async for requirement in event_pass.access.all()]


async def _treasure_count(player_id: int) -> int:
    return await BallInstance.objects.filter(player_id=player_id, deleted=False).acount()


async def _money(player_id: int) -> int:
    return await Player.objects.filter(pk=player_id).values_list("money", flat=True).afirst() or 0


async def unmet(
    player_id: int, requirements: Iterable[PassRequirement], role_ids: set[int] | None
) -> list[PassRequirement]:
    """
    The conditions this player does not meet.

    `role_ids` is what the player's Discord roles are, or `None` when they cannot be read — outside an interaction,
    or in DMs. A role condition that cannot be checked is left alone rather than failed, so nobody is thrown out of
    a pass because they used a command in DMs.
    """
    failed = []
    treasures = money = None
    for requirement in requirements:
        match requirement.kind:
            case AccessKind.ROLE:
                if role_ids is not None and requirement.role_id not in role_ids:
                    failed.append(requirement)
            case AccessKind.MAX_TREASURES | AccessKind.MIN_TREASURES:
                if treasures is None:
                    treasures = await _treasure_count(player_id)
                too_many = requirement.kind == AccessKind.MAX_TREASURES and treasures > requirement.count
                too_few = requirement.kind == AccessKind.MIN_TREASURES and treasures < requirement.count
                if too_many or too_few:
                    failed.append(requirement)
            case AccessKind.MAX_CURRENCY | AccessKind.MIN_CURRENCY:
                if money is None:
                    money = await _money(player_id)
                too_rich = requirement.kind == AccessKind.MAX_CURRENCY and money > requirement.count
                too_poor = requirement.kind == AccessKind.MIN_CURRENCY and money < requirement.count
                if too_rich or too_poor:
                    failed.append(requirement)
    return failed


def _verdict(requirements: list[PassRequirement], failed: list[PassRequirement], logic: str) -> bool:
    if not requirements:
        return True
    if logic == Logic.ANY:
        return len(failed) < len(requirements)
    return not failed


def role_ids_of(user: discord.User | discord.Member) -> set[int] | None:
    """
    The roles of the player, or `None` when Discord did not give us a member (a DM, a user object).
    """
    roles = getattr(user, "roles", None)
    if not roles:
        return None
    return {role.id for role in roles}


class Access:
    """
    What a player may do with a pass right now.
    """

    def __init__(self, allowed: bool, joined: bool, missing: list[PassRequirement], restricted: bool):
        self.allowed = allowed
        self.joined = joined
        self.missing = missing
        self.restricted = restricted

    @property
    def missing_text(self) -> list[str]:
        return [requirement.describe() for requirement in self.missing]


async def check(player_id: int, event_pass: EventPass, *, role_ids: set[int] | None, join: bool = False) -> Access:
    """
    Check a player against a pass, from a place where their Discord roles are known.

    With `join`, a player who passes is written down as taking part, and one who already was has their verdict
    refreshed. That stored verdict is what the engine reads later.
    """
    requirements = await requirements_of(event_pass)
    membership = await PlayerPass.objects.filter(player_id=player_id, event_pass_id=event_pass.pk).afirst()
    if not requirements:
        return Access(allowed=True, joined=membership is not None, missing=[], restricted=False)

    failed = await unmet(player_id, requirements, role_ids)
    allowed = _verdict(requirements, failed, event_pass.access_logic)
    if join and (allowed or membership is not None):
        # someone already taking part keeps their row, with the fresh verdict written on it. Which conditions were
        # met is kept too, so the engine can reuse the answer for the ones it cannot check on its own.
        failed_ids = {requirement.pk for requirement in failed}
        met_ids = [requirement.pk for requirement in requirements if requirement.pk not in failed_ids]
        await PlayerPass.objects.aupdate_or_create(
            player_id=player_id,
            event_pass_id=event_pass.pk,
            defaults={"eligible": allowed, "eligible_checked_at": timezone.now(), "passed": met_ids},
        )
        membership = (
            membership or await PlayerPass.objects.filter(player_id=player_id, event_pass_id=event_pass.pk).afirst()
        )
    return Access(allowed=allowed, joined=membership is not None, missing=failed, restricted=True)


async def progress_gate(player_id: int, event_pass: EventPass) -> tuple[bool, bool]:
    """
    Whether the engine may move this player's quests of a pass forward, as (one-off quests, repeating quests).

    An open pass says yes to both. On a restricted one the player must have entered. From then on the quests they
    can only do once keep going even if they stop qualifying — taking away something half finished would be unfair,
    and a beginners' pass is meant to be finished. The quests that come back every day or week are the ones worth
    closing, so they are checked again: the stored verdict covers the role conditions, the rest is counted now.

    The conditions are read once per pass here rather than once per quest, since a player usually has several
    quests of the same pass moving at the same time.
    """
    requirements = await requirements_of(event_pass)
    if not requirements:
        return (True, True)
    membership = await PlayerPass.objects.filter(player_id=player_id, event_pass_id=event_pass.pk).afirst()
    if membership is None:
        return (False, False)
    if not membership.eligible:
        return (True, False)
    live = [requirement for requirement in requirements if requirement.counts_live]
    if not live:
        return (True, True)

    # a condition is met right now if it was just counted, or — for the ones needing Discord — if it was met the
    # last time the player opened the pass. Mixing the two is what makes "any one of these" behave: someone kept in
    # by their role stays in, someone kept in by their treasure count is checked against it again.
    failed_now = {requirement.pk for requirement in await unmet(player_id, live, None)}
    remembered = set(membership.passed or [])
    live_ids = {requirement.pk for requirement in live}
    still_failing = [
        requirement
        for requirement in requirements
        if (requirement.pk in failed_now) or (requirement.pk not in live_ids and requirement.pk not in remembered)
    ]
    return (True, _verdict(requirements, still_failing, event_pass.access_logic))
