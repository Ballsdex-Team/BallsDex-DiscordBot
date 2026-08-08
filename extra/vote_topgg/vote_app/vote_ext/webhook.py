import logging
import random
from datetime import timedelta
from io import BytesIO
from typing import TYPE_CHECKING

import discord
import topgg
from django.db.models import Q
from django.utils import timezone

from ballsdex.core.image_generator.image_gen import draw_card
from bd_models.models import Ball, BallInstance, Player, Special
from preview.utils import refresh_cache
from settings.models import settings as bot_settings

from ..models import VoteRecord, VoteSettings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.extra.vote")

# Top.gg's own vote cooldown; also used here to ignore a webhook replayed for the same vote
VOTE_COOLDOWN = timedelta(hours=12)


async def _get_random_active_special() -> Special | None:
    now = timezone.now()
    population = [
        x
        async for x in Special.objects.filter(hidden=False).filter(
            Q(start_date__isnull=True) | Q(start_date__lte=now), Q(end_date__isnull=True) | Q(end_date__gte=now)
        )
    ]
    if not population:
        return None
    return random.choices(population=population, weights=[x.rarity for x in population], k=1)[0]


async def _send_dm(bot: "BallsDexBot", discord_id: int, instance: BallInstance) -> None:
    try:
        user = await bot.fetch_user(discord_id)

        ball = instance.ball
        special = instance.special
        reward_name = f"{special.name} {ball.country}" if special else ball.country

        await refresh_cache()
        image, save_kwargs = draw_card(instance)
        buffer = BytesIO()
        image.save(buffer, **save_kwargs)
        buffer.seek(0)

        await user.send(
            content=f"🎉 Thanks for voting! Here's your reward: **{reward_name}**",
            file=discord.File(buffer, "card.webp"),
        )
    except discord.Forbidden:
        log.info("Could not DM player %s their vote reward (DMs closed)", discord_id)
    except Exception:
        log.exception("Failed to DM vote reward to player %s", discord_id)


async def grant_reward(bot: "BallsDexBot", vote_settings: VoteSettings, discord_id: int) -> None:
    player, _ = await Player.objects.aget_or_create(discord_id=discord_id)

    last_vote = await VoteRecord.objects.filter(player=player).order_by("-voted_at").afirst()
    if last_vote is not None and timezone.now() - last_vote.voted_at < VOTE_COOLDOWN:
        log.info("Duplicate vote webhook for player %s ignored (already rewarded within 12h)", discord_id)
        return

    balls = [
        x
        async for x in Ball.objects.filter(
            enabled=True, tradeable=True, rarity__range=(vote_settings.min_rarity, vote_settings.max_rarity)
        )
    ]
    reward = None
    if balls:
        ball = random.choices(population=balls, weights=[x.rarity for x in balls], k=1)[0]
        special = None
        if random.random() < vote_settings.special_chance:
            special = await _get_random_active_special()
        reward = await BallInstance.objects.acreate(
            player=player,
            ball=ball,
            special=special,
            health_bonus=random.randint(-bot_settings.max_health_bonus, bot_settings.max_health_bonus),
            attack_bonus=random.randint(-bot_settings.max_attack_bonus, bot_settings.max_attack_bonus),
        )
        await _send_dm(bot, discord_id, reward)
    else:
        log.warning("No ball available in the configured vote rarity range, no reward granted for %s", discord_id)

    await VoteRecord.objects.acreate(player=player, reward=reward)


async def start_webhook_server(bot: "BallsDexBot", vote_settings: VoteSettings) -> "topgg.Webhooks | None":
    if not vote_settings.webhook_secret:
        log.info("No vote webhook secret configured, the vote webhook server stays disabled.")
        return None

    webhooks = topgg.Webhooks("/webhook/topgg", vote_settings.webhook_secret, port=vote_settings.webhook_port)

    @webhooks.on(topgg.PayloadType.VOTE_CREATE)
    async def on_vote(payload: "topgg.VoteCreatePayload", trace: str):
        await grant_reward(bot, vote_settings, int(payload.user.platform_id))

    await webhooks.start()
    log.info("Vote webhook server started on port %s", vote_settings.webhook_port)
    return webhooks
