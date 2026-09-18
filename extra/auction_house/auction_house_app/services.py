"""
Shared auction-house logic used by both the AuctionHouse (/auction) and TreasureSale
(/sell) cogs, kept as plain functions rather than cog methods so neither cog
depends on the other's instance.
"""

import datetime
import logging

import discord
from asgiref.sync import sync_to_async
from currency_app.ledger import adjust_money
from currency_app.models import BerryTransaction
from django.db import transaction
from django.utils import timezone

from ballsdex.core.utils.utils import member_role_ids
from bd_models.models import BallInstance

from . import pricing
from .models import (
    AuctionAdminRole,
    AuctionBidBlacklist,
    AuctionBidBlacklistRole,
    AuctionBoosterRole,
    AuctionListing,
    AuctionSettings,
    DirectSaleRecord,
    FeaturedAuction,
    FeaturedAuctionItem,
    HotelStock,
    SpecialPriceModifier,
    StatBonusModifier,
    get_hotel_player_sync,
)

log = logging.getLogger(__name__)


async def safe_settle(func, *args, **kwargs):
    """
    Runs a synchronous settlement function (one of the `_xxx` methods below or on a cog,
    always wrapped in `transaction.atomic()`) via `sync_to_async`.

    Every settlement function is fully atomic, so ANY failure — expected (a `RuntimeError`
    with a user-facing message) or not — rolls back cleanly: coins and treasures are never
    partially applied. Unexpected exceptions are logged here and re-raised as a safe, generic
    `RuntimeError`, so every call site only ever needs to catch `RuntimeError`.
    """
    try:
        return await sync_to_async(func)(*args, **kwargs)
    except RuntimeError:
        raise
    except Exception:
        log.exception("Settlement call failed unexpectedly: %s", getattr(func, "__qualname__", func))
        raise RuntimeError("Something went wrong — nothing was charged or changed. Please try again.")


async def load_pricing_context() -> tuple[AuctionSettings, dict[int, int], dict[int, int]]:
    auction_settings = await AuctionSettings.aload()
    special_modifiers = {sm.special_id: sm.percent async for sm in SpecialPriceModifier.objects.all()}
    stat_modifiers = {sm.value: sm.percent async for sm in StatBonusModifier.objects.all()}
    return auction_settings, special_modifiers, stat_modifiers


async def get_total_booster_bonus(user: discord.User | discord.Member, server_id: int, field: str) -> int:
    """
    Sum of every matching AuctionBoosterRole's `field` ("buy_discount_percent" or
    "sell_bonus_percent") for `user` in `server_id` — a player with several qualifying
    roles gets all of their bonuses added together.
    """
    if not isinstance(user, discord.Member):
        return 0
    role_ids = member_role_ids(user)
    if not role_ids:
        return 0
    total = 0
    async for booster in AuctionBoosterRole.objects.filter(server_id=server_id, role_id__in=role_ids):
        total += getattr(booster, field)
    return total


async def is_excluded_ball(ball_id: int, auction_settings: AuctionSettings) -> bool:
    return await auction_settings.excluded_balls.filter(pk=ball_id).aexists()


async def is_blacklisted_bidder(user: discord.User | discord.Member, server_id: int) -> bool:
    if await AuctionBidBlacklist.objects.filter(discord_id=user.id).aexists():
        return True
    if isinstance(user, discord.Member):
        role_ids = member_role_ids(user)
        if role_ids and await AuctionBidBlacklistRole.objects.filter(
            server_id=server_id, role_id__in=role_ids
        ).aexists():
            return True
    return False


async def is_auction_admin(user: discord.User | discord.Member, server_id: int) -> bool:
    if not isinstance(user, discord.Member):
        return False
    role_ids = member_role_ids(user)
    if not role_ids:
        return False
    return await AuctionAdminRole.objects.filter(server_id=server_id, role_id__in=role_ids).aexists()


async def is_already_committed(instance: "BallInstance") -> bool:
    """
    Whether this treasure is currently tied up somewhere in the auction house.

    Only *live* commitments count. Closed records (an expired listing, stock Buggy already
    sold or gave away, a finished featured auction) are kept as history, and a treasure that
    came back from one of those must be sellable and listable again.
    """
    if await AuctionListing.objects.filter(instance=instance, status=AuctionListing.Status.ACTIVE).aexists():
        return True
    if await HotelStock.objects.filter(instance=instance, status=HotelStock.Status.AVAILABLE).aexists():
        return True
    return await FeaturedAuctionItem.objects.filter(
        instance=instance, auction__status=FeaturedAuction.Status.ACTIVE
    ).aexists()


async def direct_sale_count_today(player_id: int) -> int:
    """Global (all-servers) count of direct sales made by this player today."""
    today = timezone.localdate()
    return await DirectSaleRecord.objects.filter(player_id=player_id, sold_at__date=today).acount()


def next_daily_sale_reset() -> datetime.datetime:
    """When the direct-sale daily limit resets (local midnight tonight)."""
    tomorrow = timezone.localdate() + datetime.timedelta(days=1)
    return timezone.make_aware(datetime.datetime.combine(tomorrow, datetime.time.min))


def direct_sale_price_for(
    instance: "BallInstance", auction_settings: AuctionSettings, stat_modifiers: dict[int, int], bonus_percent: int
) -> int:
    return pricing.direct_sale_price(instance, auction_settings, stat_modifiers, bonus_percent)


def settle_direct_sale(instance_id: int, price: int, resale_price: int, server_id: int, expected_player_id: int):
    """
    Pays the seller, transfers the treasure to Buggy, stocks it, and logs the sale.

    Everything here runs inside one atomic transaction, so any failure — including the
    `expected_player_id` mismatch below — rolls back cleanly: no money is ever paid without
    the treasure actually changing hands, and vice versa. `expected_player_id` guards against
    a race where the instance changed hands between the confirm prompt and this call (e.g. a
    concurrent trade or a second /sell on the same treasure).
    """
    with transaction.atomic():
        # `special` is a nullable FK — Postgres refuses FOR UPDATE across the nullable side of an
        # outer join, so the lock is restricted to the BallInstance row itself via `of=("self",)`.
        instance = (
            BallInstance.objects.select_related("player", "ball", "special")
            .select_for_update(of=("self",))
            .get(pk=instance_id)
        )
        if instance.player_id != expected_player_id:
            raise RuntimeError("This treasure changed hands before the sale could complete — nothing was charged.")

        player = instance.player
        ball_name = instance.countryball.country
        special_name = instance.specialcard.name if instance.specialcard else None
        attack_bonus = instance.attack_bonus
        health_bonus = instance.health_bonus

        adjust_money(
            player,
            price,
            reason=BerryTransaction.Reason.AUCTION_SELL,
            description=f"Sold {ball_name}{f' [{special_name}]' if special_name else ''} to Buggy",
            server_id=server_id,
        )

        hotel = get_hotel_player_sync()
        instance.player = hotel
        instance.favorite = False
        instance.save(update_fields=["player", "favorite"])

        HotelStock.objects.create(
            instance=instance, server_id=server_id, buyout_price=price, resale_price=resale_price
        )
        DirectSaleRecord.objects.create(
            player_id=player.pk,
            server_id=server_id,
            instance_id=instance_id,
            ball_name=ball_name,
            special_name=special_name,
            attack_bonus=attack_bonus,
            health_bonus=health_bonus,
            price=price,
        )
        log.info(
            "Direct sale: player=%s server=%s treasure=#%0X (%s%s, atk%+d hp%+d) price=%s",
            player.discord_id,
            server_id,
            instance_id,
            ball_name,
            f" [{special_name}]" if special_name else "",
            attack_bonus,
            health_bonus,
            price,
        )
