"""
Giving the rewards of a pass, exactly once.

Every reward goes through `grant`, which writes a `RewardGrant` row first. That row carries a unique constraint on
(player, source, source id, period), so a double click, a retry or two claims racing each other can only ever
insert it once — whoever loses the race gets nothing and knows it. The berries and treasures are only handed out
after that row exists, in the same transaction, so a failure rolls the whole thing back.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from currency_app.ledger import adjust_money
from currency_app.models import BerryTransaction
from django.db import IntegrityError, transaction
from django.utils import timezone

from bd_models.models import Ball, BallInstance, balls, frame_entry, groups
from settings.models import settings
from settings.utils import format_currency

from .models import BonusMode, EventPass, Reward, RewardChoice, RewardGrant, RewardKind, RewardLine, RewardMode, Source

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("eventpass")


@dataclass
class GrantResult:
    lines: list[str] = field(default_factory=list)
    instances: list[BallInstance] = field(default_factory=list)
    berries: int = 0
    # set when the reward is a choice: nothing was handed out yet, the player still has to pick
    choice_id: int | None = None
    choice_label: str = ""

    @property
    def summary(self) -> str:
        return "\n".join(f"- {line}" for line in self.lines)


# 25 is what a Discord select menu holds
MAX_OPTIONS = 25


def pool_balls(line: RewardLine) -> list[Ball]:
    """
    The treasures a pool line can give, from the caches so no query is needed.

    Only enabled treasures are ever drawn: a disabled one is not in the game, handing it out as a reward would be a
    surprise nobody asked for.
    """
    # `.all()` reads the prefetch the pass loads with its rewards; `values_list` would query every time, and
    # this runs from the async code that draws the pass
    excluded = {ball.pk for ball in line.exclude_balls.all()} if line.pk else set()
    group = groups.get(line.group_id) if line.group_id else None
    found = []
    for ball in balls.values():
        if not ball.enabled or ball.pk in excluded:
            continue
        if group is not None and ball.pk not in group._ball_ids:
            continue
        if line.group_id and group is None:
            continue
        if line.regime_id and ball.regime_id != line.regime_id:
            continue
        if line.economy_id and ball.economy_id != line.economy_id:
            continue
        if line.min_rarity is not None and ball.rarity < line.min_rarity:
            continue
        if line.max_rarity is not None and ball.rarity > line.max_rarity:
            continue
        found.append(ball)
    found.sort(key=lambda ball: (ball.rarity, ball.country))
    return found


def _frame_for(ball: Ball, frame_key: str) -> dict | None:
    frame = frame_entry(ball, frame_key)
    if frame_key and frame is None:
        log.warning("The frame %s of %s does not exist, the reward is given without it", frame_key, ball.country)
    return frame


def _give_treasure(
    line: RewardLine, player_id: int, server_id: int | None, channel_id: int | None, ball: Ball | None = None
) -> list[BallInstance]:
    """
    Create the treasures of one line. `ball` overrides the one the line names, for a pool line whose treasure was
    drawn or picked by the player.
    """
    ball = ball or balls.get(line.ball_id) or line.ball
    if ball is None:
        return []
    frame = _frame_for(ball, line.frame_key)
    created = []
    for _ in range(max(line.quantity, 1)):
        if line.bonus_mode == BonusMode.RANDOM:
            attack = random.randint(-settings.max_attack_bonus, settings.max_attack_bonus)
            health = random.randint(-settings.max_health_bonus, settings.max_health_bonus)
        elif line.bonus_mode == BonusMode.FIXED:
            attack, health = line.attack_bonus, line.health_bonus
        else:
            attack = health = 0
        instance = BallInstance(
            player_id=player_id,
            ball_id=ball.pk,
            special_id=line.special_id,
            attack_bonus=attack,
            health_bonus=health,
            tradeable=line.tradeable,
            server_id=server_id,
            extra_data=dict(frame) if frame else {},
        )
        # read by the game event bus, to congratulate the player where they claimed instead of where they played
        if channel_id:
            instance._notify_channel_id = channel_id  # type: ignore[attr-defined]
        instance.save()
        created.append(instance)
    return created


def _grant(
    player_id: int,
    event_pass: EventPass,
    reward: Reward,
    *,
    source: str,
    source_id: int,
    period: str = "",
    server_id: int | None = None,
    channel_id: int | None = None,
    label: str = "",
) -> GrantResult | None:
    result = GrantResult()
    with transaction.atomic():
        try:
            grant = RewardGrant.objects.create(
                player_id=player_id,
                event_pass_id=event_pass.pk,
                reward_id=reward.pk,
                source=source,
                source_id=source_id,
                period=period,
            )
        except IntegrityError:
            # already given: another click, another shard or a retry got there first
            return None

        lines = list(reward.lines.all())
        if reward.mode == RewardMode.ALL:
            for line in lines:
                _give_line(result, line, player_id, event_pass, reward, server_id, channel_id)
        else:
            # berries never take part in a pick or a draw: a reward saying "500 berries and one of these three
            # cards" should not sometimes hand over the berries instead of a card
            treasures = []
            for line in lines:
                if line.kind == RewardKind.BERRIES:
                    _give_line(result, line, player_id, event_pass, reward, server_id, channel_id)
                else:
                    treasures.append(line)
            if reward.mode == RewardMode.RANDOM:
                for line, ball in _drawn(treasures, reward.pick):
                    _give_line(result, line, player_id, event_pass, reward, server_id, channel_id, ball=ball)
            else:
                _offer_choice(result, treasures, player_id, event_pass, reward, grant, label=label)

        grant.summary = result.summary
        grant.save(update_fields=("summary",))
    return result


def _give_line(
    result: GrantResult,
    line: RewardLine,
    player_id: int,
    event_pass: EventPass,
    reward: Reward,
    server_id: int | None,
    channel_id: int | None,
    ball: Ball | None = None,
) -> None:
    if line.kind == RewardKind.BERRIES:
        if not line.amount:
            return
        adjust_money(
            player_id,
            line.amount,
            reason=BerryTransaction.Reason.EVENT_PASS,
            description=f"{event_pass.name}: {reward.name}"[: BerryTransaction.DESCRIPTION_MAX_LENGTH],
            server_id=server_id,
        )
        result.berries += line.amount
        result.lines.append(format_currency(line.amount, False))
        return
    instances = _give_treasure(line, player_id, server_id, channel_id, ball=ball)
    if not instances:
        return
    result.instances.extend(instances)
    result.lines.append(_line_text(line, ball))


def _line_text(line: RewardLine, ball: Ball | None) -> str:
    """
    What a line gave. A pool line says the treasure it landed on rather than describing the pool again.
    """
    if ball is None:
        return str(line)
    special = line.cached_special
    text = f"{line.quantity}x {special.name + ' ' if special else ''}{ball.country}"
    return f"{text} (framed)" if line.frame_key else text


def _options(lines: list[RewardLine]) -> list[tuple[RewardLine, Ball | None]]:
    """
    Everything a choice or a draw can land on: a named line counts once, a pool line offers each of its treasures.
    """
    found: list[tuple[RewardLine, Ball | None]] = []
    for line in lines:
        if line.kind == RewardKind.BERRIES or not line.is_pool:
            found.append((line, None))
            continue
        found.extend((line, ball) for ball in pool_balls(line))
    return found


def _drawn(lines: list[RewardLine], pick: int) -> list[tuple[RewardLine, Ball | None]]:
    """
    Draw `pick` options, avoiding repeats while there are enough of them to go around.
    """
    options = _options(lines)
    if not options:
        return []
    count = max(pick, 1)
    drawn = random.sample(options, min(count, len(options)))
    while len(drawn) < count:
        drawn.append(random.choice(options))
    return drawn


def _offer_choice(
    result: GrantResult,
    lines: list[RewardLine],
    player_id: int,
    event_pass: EventPass,
    reward: Reward,
    grant: RewardGrant,
    *,
    label: str,
) -> None:
    """
    Reserve a reward the player still has to pick.

    Nothing is handed out here. The options are written down next to the grant that reserves them, so the player can
    close the pass and come back to a choice that has not moved — and can never claim it twice.
    """
    options = _options(lines)
    treasures = [ball or balls.get(line.ball_id) or line.ball for line, ball in options]
    ball_ids = [ball.pk for ball in treasures if ball is not None]
    picks = max(reward.pick, 1)
    if len(ball_ids) <= picks:
        # not enough to choose from: there is nothing to decide, give them all
        for line, ball in options:
            _give_line(result, line, player_id, event_pass, reward, None, None, ball=ball)
        return
    limit = min(reward.offer or MAX_OPTIONS, MAX_OPTIONS)
    if len(ball_ids) > limit:
        ball_ids = random.sample(ball_ids, limit)
    choice = RewardChoice.objects.create(
        player_id=player_id,
        event_pass_id=event_pass.pk,
        grant=grant,
        reward_id=reward.pk,
        label=label[:128],
        options=ball_ids,
        picks=picks,
    )
    result.choice_id = choice.pk
    result.choice_label = label
    result.lines.append(f"{picks} to pick out of {len(ball_ids)}")


async def grant(
    player_id: int,
    event_pass: EventPass,
    reward: Reward | None,
    *,
    source: Source | str,
    source_id: int,
    period: str = "",
    server_id: int | None = None,
    channel_id: int | None = None,
    label: str = "",
) -> GrantResult | None:
    """
    Give a reward bundle to a player, once and only once.

    Returns
    -------
    GrantResult | None
        What the player got, or `None` when they already got it (or there was nothing to give). A reward the player
        has to pick comes back with `choice_id` set and nothing handed out yet.
    """
    if reward is None:
        return None
    return await sync_to_async(_grant)(
        player_id,
        event_pass,
        reward,
        source=str(source),
        source_id=source_id,
        period=period,
        server_id=server_id,
        channel_id=channel_id,
        label=label,
    )


def _resolve(choice_id: int, ball_ids: list[int], server_id: int | None, channel_id: int | None) -> GrantResult:
    """
    Hand out the treasures a player picked, once.

    The row is locked and checked for `resolved_at` inside the transaction, so two clicks on the select menu cannot
    both go through — the second one finds the choice already resolved and gets nothing.
    """
    result = GrantResult()
    with transaction.atomic():
        # `of` keeps the lock on the choice row alone: reward is nullable, so joining it would make Postgres
        # refuse a FOR UPDATE on the outer side of the join
        choice = (
            RewardChoice.objects.select_for_update(of=("self",)).select_related("reward").filter(pk=choice_id).first()
        )
        if choice is None or choice.resolved_at is not None:
            return result
        allowed = set(choice.options)
        wanted = [ball_id for ball_id in ball_ids if ball_id in allowed][: max(choice.picks, 1)]
        if not wanted:
            return result

        # a pool line carries the settings of the treasure (special, frame, bonuses); fall back to a plain one
        line = None
        if choice.reward_id:
            line = choice.reward.lines.filter(kind=RewardKind.TREASURE).first()
        if line is None:
            line = RewardLine(kind=RewardKind.TREASURE, quantity=1, bonus_mode=BonusMode.RANDOM)

        for ball_id in wanted:
            ball = balls.get(ball_id)
            if ball is None:
                continue
            result.instances.extend(_give_treasure(line, choice.player_id, server_id, channel_id, ball=ball))
            result.lines.append(_line_text(line, ball))

        choice.chosen = wanted
        choice.resolved_at = timezone.now()
        choice.save(update_fields=("chosen", "resolved_at"))
        RewardGrant.objects.filter(pk=choice.grant_id).update(summary=result.summary)
    return result


async def resolve_choice(
    choice_id: int, ball_ids: list[int], *, server_id: int | None = None, channel_id: int | None = None
) -> GrantResult:
    """
    Give a player the treasures they picked from a pending choice.
    """
    return await sync_to_async(_resolve)(choice_id, ball_ids, server_id, channel_id)


async def pending_choices(player_id: int, event_pass: EventPass) -> list[RewardChoice]:
    """
    The rewards this player still has to pick on a pass, oldest first.
    """
    return [
        choice
        async for choice in RewardChoice.objects.filter(
            player_id=player_id, event_pass_id=event_pass.pk, resolved_at__isnull=True
        ).order_by("pk")
    ]


def reward_preview(reward: Reward | None, bot: BallsDexBot | None = None) -> str:
    """
    A short "5,000 berries + 1x Birthday Token" used in the pass, before anything is claimed.
    """
    if reward is None:
        return ""
    parts = []
    for line in reward.lines.all():
        if line.kind == RewardKind.BERRIES:
            parts.append(format_currency(line.amount, False, bot))
        else:
            parts.append(str(line))
    if not parts:
        return ""
    if reward.mode == RewardMode.ALL:
        return " + ".join(parts)
    # berries are given whatever the mode, so they are listed apart from what is picked or drawn
    lines = list(reward.lines.all())
    berries = [line for line in lines if line.kind == RewardKind.BERRIES]
    treasures = [line for line in lines if line.kind != RewardKind.BERRIES]
    # a pool is worth naming by its size: "1 of 9 Straw Hats" says more than "1x Straw Hats"
    options = sum(len(pool_balls(line)) if line.is_pool else 1 for line in treasures)
    if len(treasures) == 1 and treasures[0].is_pool:
        what = treasures[0].pool_description()
    else:
        what = " or ".join(str(line) for line in treasures)
    if options > 1:
        verb = "your pick" if reward.mode == RewardMode.CHOICE else "at random"
        what = f"{reward.pick} of {options} {what} ({verb})"
    given = [format_currency(line.amount, False, bot) for line in berries]
    return " + ".join([*given, what] if what else given)
