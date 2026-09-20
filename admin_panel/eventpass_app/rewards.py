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

from bd_models.models import Ball, BallInstance, balls, frame_entry
from settings.models import settings
from settings.utils import format_currency

from .models import BonusMode, EventPass, Reward, RewardGrant, RewardKind, RewardLine, Source

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("eventpass")


@dataclass
class GrantResult:
    lines: list[str] = field(default_factory=list)
    instances: list[BallInstance] = field(default_factory=list)
    berries: int = 0

    @property
    def summary(self) -> str:
        return "\n".join(f"- {line}" for line in self.lines)


def _frame_for(ball: Ball, frame_key: str) -> dict | None:
    frame = frame_entry(ball, frame_key)
    if frame_key and frame is None:
        log.warning("The frame %s of %s does not exist, the reward is given without it", frame_key, ball.country)
    return frame


def _give_treasure(
    line: RewardLine, player_id: int, server_id: int | None, channel_id: int | None
) -> list[BallInstance]:
    ball = balls.get(line.ball_id) or line.ball
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

        for line in reward.lines.all():
            if line.kind == RewardKind.BERRIES:
                if not line.amount:
                    continue
                adjust_money(
                    player_id,
                    line.amount,
                    reason=BerryTransaction.Reason.EVENT_PASS,
                    description=f"{event_pass.name}: {reward.name}"[: BerryTransaction.DESCRIPTION_MAX_LENGTH],
                    server_id=server_id,
                )
                result.berries += line.amount
                result.lines.append(format_currency(line.amount, False))
            else:
                instances = _give_treasure(line, player_id, server_id, channel_id)
                if not instances:
                    continue
                result.instances.extend(instances)
                result.lines.append(str(line))

        grant.summary = result.summary
        grant.save(update_fields=("summary",))
    return result


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
) -> GrantResult | None:
    """
    Give a reward bundle to a player, once and only once.

    Returns
    -------
    GrantResult | None
        What the player got, or `None` when they already got it (or there was nothing to give).
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
    )


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
    return " + ".join(parts)
