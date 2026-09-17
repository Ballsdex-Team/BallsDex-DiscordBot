"""
Requirement checks and claims of collector cards. Every function here is synchronous, call them with `sync_to_async`.
"""

import random
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Literal

from collector_app.models import CollectorInstance, CollectorRequirement, CollectorTier, CollectorTierLevel
from currency_app.ledger import adjust_money
from currency_app.models import BerryTransaction
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from bd_models.models import BallInstance, Player
from bd_models.signals import notify_ownership_change
from settings.models import settings

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from ballsdex.core.bot import BallsDexBot


@dataclass
class RequirementStatus:
    requirement: CollectorRequirement
    owned: int

    @property
    def met(self) -> bool:
        return self.owned >= self.requirement.amount

    def label(self, bot: "BallsDexBot | None" = None) -> str:
        ball = self.requirement.cached_ball
        special = self.requirement.cached_special
        name = " ".join(x for x in (special.name if special else "", ball.country if ball else "") if x)
        emoji = bot.get_emoji(ball.emoji_id) if bot and ball else None
        return f"{f'{emoji} ' if emoji else ''}{name or settings.plural_collectible_name}"

    def describe(self, bot: "BallsDexBot | None" = None) -> str:
        text = (
            f"{'✅' if self.met else '❌'} {min(self.owned, self.requirement.amount)}/{self.requirement.amount} "
            f"{self.label(bot)}"
        )
        if self.requirement.delete_balls:
            text += " *(used up when claiming)*"
        return text


@dataclass
class ClaimResult:
    status: Literal["claimed", "already_claimed", "unavailable", "missing", "not_enough_money", "locked"]
    card: BallInstance | None = None
    statuses: list[RequirementStatus] = field(default_factory=list)

    @property
    def missing(self) -> list[RequirementStatus]:
        return [status for status in self.statuses if not status.met]


def collector_card_special_ids() -> set[int]:
    """
    Specials given to collector cards. Treasures with one of these never count toward requirements, otherwise a
    Luffy collector card would count as the Luffy required to keep it.
    """
    ids = set(CollectorTierLevel.objects.filter(special__isnull=False).values_list("special_id", flat=True))
    ids.update(CollectorTier.objects.filter(special__isnull=False).values_list("special_id", flat=True))
    return ids


def requirement_queryset(
    player_id: int, requirement: CollectorRequirement, excluded_specials: set[int]
) -> "QuerySet[BallInstance]":
    queryset = BallInstance.objects.filter(player_id=player_id)
    if requirement.ball_id:
        queryset = queryset.filter(ball_id=requirement.ball_id)
    if requirement.special_id:
        queryset = queryset.filter(special_id=requirement.special_id)
    elif excluded_specials:
        queryset = queryset.exclude(special_id__in=excluded_specials)
    return queryset


def evaluate_requirements(
    player_id: int, requirements: list[CollectorRequirement], excluded_specials: set[int] | None = None
) -> list[RequirementStatus]:
    if excluded_specials is None:
        excluded_specials = collector_card_special_ids()
    return [
        RequirementStatus(requirement, requirement_queryset(player_id, requirement, excluded_specials).count())
        for requirement in requirements
    ]


def tier_requirements(tier: CollectorTier | CollectorInstance, *, include_consumed: bool = True):
    queryset = CollectorRequirement.objects.filter(
        collector_id=tier.collector_id, level_id=tier.level_id
    ).select_related("ball", "special")
    if not include_consumed:
        queryset = queryset.filter(delete_balls=False)
    return list(queryset.order_by("amount", "pk"))


def is_claimed(player_id: int, tier: CollectorTier) -> bool:
    return CollectorInstance.objects.filter(
        player_id=player_id, collector_id=tier.collector_id, level_id=tier.level_id, revoked_at__isnull=True
    ).exists()


def claim_tier(player_id: int, tier_id: int, server_id: int | None) -> ClaimResult:
    """
    Claim a collector tier for a player: check the requirements, take the price and the used up treasures, then give
    the card. The player row is locked so a double click can't claim twice.
    """
    now = timezone.now()
    with transaction.atomic():
        player = Player.objects.select_for_update().get(pk=player_id)
        tier = CollectorTier.objects.select_related("collector", "level").get(pk=tier_id)
        if not tier.enabled or not tier.level.claimable or not tier.collector.active or not tier.collector.ball_id:
            return ClaimResult("unavailable")
        if is_claimed(player_id, tier):
            return ClaimResult("already_claimed")

        requirements = tier_requirements(tier)
        excluded_specials = collector_card_special_ids()
        statuses = evaluate_requirements(player_id, requirements, excluded_specials)
        if any(not status.met for status in statuses):
            return ClaimResult("missing", statuses=statuses)
        if tier.price and player.money < tier.price:
            return ClaimResult("not_enough_money", statuses=statuses)

        # pick the treasures used up first, favorites last, so nothing changes if some are locked in a trade
        consumed: list[int] = []
        for requirement in requirements:
            if not requirement.delete_balls:
                continue
            ids = list(
                requirement_queryset(player_id, requirement, excluded_specials)
                .exclude(pk__in=consumed)
                .filter(Q(locked__isnull=True) | Q(locked__lt=now - timedelta(minutes=30)))
                .order_by("favorite", "-catch_date")
                .values_list("pk", flat=True)[: requirement.amount]
            )
            if len(ids) < requirement.amount:
                return ClaimResult("locked", statuses=statuses)
            consumed.extend(ids)

        if tier.price:
            adjust_money(
                player,
                -tier.price,
                reason=BerryTransaction.Reason.COLLECTOR_CLAIM,
                description=f"Claimed {tier.collector.name} ({tier.level.name})",
                server_id=server_id,
            )
        if consumed:
            BallInstance.objects.filter(pk__in=consumed).update(deleted=True)
            notify_ownership_change(lost={player_id: consumed})

        card = BallInstance.objects.create(
            player_id=player_id,
            ball_id=tier.collector.ball_id,
            special_id=tier.card_special_id,
            tradeable=tier.tradeable,
            health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
            attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
            catch_date=now,
            server_id=server_id,
        )
        CollectorInstance.objects.create(
            player_id=player_id,
            collector_id=tier.collector_id,
            level_id=tier.level_id,
            ball_instance=card,
            claimed_at=now,
            monitored=tier.level.monitored,
        )
    return ClaimResult("claimed", card=card, statuses=statuses)
