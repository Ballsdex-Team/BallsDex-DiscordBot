import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import discord
from asgiref.sync import sync_to_async
from currency_app.models import Item as ItemModel
from discord import app_commands
from discord.ext import commands
from discord.utils import format_dt
from django.db import transaction
from django.utils import timezone
from pack_models.models import PackBonusRole, PackResource, PackSettings

from bd_models.models import Ball, BallInstance, Player
from settings.models import settings
from settings.utils import format_currency

from .components import ShopMenuSource, ShopPages

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


@dataclass
class DailyClaim:
    allowed: bool
    uses: int = 0
    max_uses: int = 0
    streak: int = 0
    cooldown_until: datetime | None = None
    streak_bonus: bool = False
    lucky_bonus: bool = False


def claim_daily_pack(player_id: int, role_bonus: int, pack_settings: PackSettings) -> DailyClaim:
    """
    Take one daily pack use for a player, starting a new daily cycle and granting bonus packs when needed.
    The resource row is locked, so the same pack can't be claimed twice by spamming the command.
    """
    now = timezone.now()
    with transaction.atomic():
        resource, _ = PackResource.objects.select_for_update().get_or_create(player_id=player_id)
        if resource.daily_cooldown_active():
            return DailyClaim(allowed=False, cooldown_until=resource.daily_cooldown + timedelta(days=1))  # type: ignore

        streak_bonus = lucky_bonus = False
        if resource.daily_cooldown is not None or resource.daily_uses == 0:
            # the previous cycle is over, this pack starts a new one
            last_start = resource.daily_cycle_started_at
            if last_start is not None and now - last_start <= timedelta(hours=pack_settings.streak_grace_hours):
                resource.daily_streak += 1
            else:
                resource.daily_streak = 1
            resource.daily_cycle_started_at = now
            resource.daily_cooldown = None
            resource.daily_uses = 0
            resource.daily_bonus_uses = 0
            resource.daily_bonus_rolled = False
            if pack_settings.streak_bonus_days and resource.daily_streak % pack_settings.streak_bonus_days == 0:
                resource.daily_bonus_uses += 1
                streak_bonus = True

        max_uses = pack_settings.daily_uses + role_bonus + resource.daily_bonus_uses
        if resource.daily_uses >= max_uses:
            # only happens if the player lost a bonus role after opening their packs
            resource.daily_cooldown = now
            resource.save()
            return DailyClaim(allowed=False, cooldown_until=now + timedelta(days=1))

        resource.daily_uses += 1
        if resource.daily_uses >= max_uses and pack_settings.bonus_daily_chance and not resource.daily_bonus_rolled:
            resource.daily_bonus_rolled = True
            if random.random() * 100 < pack_settings.bonus_daily_chance:
                resource.daily_bonus_uses += 1
                max_uses += 1
                lucky_bonus = True
        if resource.daily_uses >= max_uses:
            resource.daily_cooldown = now
        resource.save()

    return DailyClaim(
        allowed=True,
        uses=resource.daily_uses,
        max_uses=max_uses,
        streak=resource.daily_streak,
        cooldown_until=now + timedelta(days=1) if resource.daily_cooldown else None,
        streak_bonus=streak_bonus,
        lucky_bonus=lucky_bonus,
    )


class Pack(commands.GroupCog):
    """
    Claim a daily/weekly pack!
    """

    def __init__(self, bot: "BallsDexBot", pack_settings: PackSettings) -> None:
        self.bot = bot
        self.pack_settings = pack_settings

    @commands.group()
    async def pack(self, ctx: commands.Context["BallsDexBot"]):
        """
        Pack prefix commands.
        """
        pass

    @pack.command()
    @commands.is_owner()
    async def reloadconf(self, ctx: commands.Context["BallsDexBot"]):
        """
        Reload pack configuration from database.
        """
        assert self.bot.user
        try:
            await self.pack_settings.arefresh_from_db()
        except Exception:
            await ctx.send(
                f"Failed to refresh configuration from database. Use **{self.bot.user.mention} logs** "
                "to check the error."
            )
        else:
            await ctx.message.add_reaction("✅")

    async def _role_bonus(self, interaction: discord.Interaction["BallsDexBot"]) -> int:
        if interaction.guild_id is None or not isinstance(interaction.user, discord.Member):
            return 0
        role_ids = [role.id for role in interaction.user.roles]
        if not role_ids:
            return 0
        bonuses = PackBonusRole.objects.filter(server_id=interaction.guild_id, role_id__in=role_ids)
        return sum([bonus async for bonus in bonuses.values_list("bonus_daily_uses", flat=True)])

    @app_commands.command(name="daily")
    async def daily(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Claim your daily packs!
        """
        await self.pack_settings.arefresh_from_db()
        if not self.pack_settings.min_rarity_daily or not self.pack_settings.max_rarity_daily:
            await interaction.response.send_message(
                "Daily packs are not configured. Contact support if this persists.", ephemeral=True
            )
            return

        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        role_bonus = await self._role_bonus(interaction)
        claim = await sync_to_async(claim_daily_pack)(player.pk, role_bonus, self.pack_settings)
        if not claim.allowed:
            await interaction.response.send_message(
                f"You've used all daily packs. Come back {format_dt(claim.cooldown_until, style='R')}!",  # type: ignore
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        balls = [
            x
            async for x in Ball.objects.filter(
                enabled=True,
                tradeable=True,
                rarity__range=(self.pack_settings.min_rarity_daily, self.pack_settings.max_rarity_daily),
            )
        ]
        ball = await self._get_random_countryball(balls)
        rarity = ball.rarity
        instance = await BallInstance.objects.acreate(
            player=player,
            ball=ball,
            health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
            attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
            server_id=interaction.guild_id,
        )
        embed = discord.Embed(title=f"🎁 You got {ball.country}!", color=settings.embed_colour)
        embed.description = f"📖 **Rarity:** {rarity}\n❤️ **Health:** {ball.health}\n⚔️ **Attack:** {ball.attack}\n"
        if claim.streak_bonus:
            embed.description += f"\n🔥 **{claim.streak} days streak!** You earned a bonus daily pack today."
        if claim.lucky_bonus:
            embed.description += "\n🍀 **Lucky!** You unlocked a bonus daily pack."
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        footer_text = f"Uses: {claim.uses}/{claim.max_uses}"
        if claim.streak:
            footer_text += f" • Streak: {claim.streak} day{'s' if claim.streak > 1 else ''}"
        if claim.cooldown_until:
            footer_text += " • Come back tomorrow."
        embed.set_footer(text=footer_text)
        with ThreadPoolExecutor() as pool:
            buffer = await interaction.client.loop.run_in_executor(pool, instance.draw_card)
        file = discord.File(buffer, "card.webp")
        embed.set_image(url="attachment://card.webp")
        await interaction.followup.send(embed=embed, file=file)

    @app_commands.command(name="weekly")
    async def weekly(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Claim your weekly pack!
        """
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        resource, _ = await PackResource.objects.aget_or_create(player=player)
        if await resource.is_weekly_on_cooldown():
            await interaction.response.send_message(
                f"You've used all weekly packs. "
                f"Come back {format_dt(resource.weekly_cooldown + timedelta(days=7), style='R')}!",  # type: ignore
                ephemeral=True,
            )
            return
        if not self.pack_settings.min_rarity_weekly or not self.pack_settings.max_rarity_weekly:
            await interaction.response.send_message(
                "Weekly packs are not configured. Contact support if this persists.", ephemeral=True
            )
            return

        if resource.weekly_cooldown is not None:
            await resource.remove_weekly_cooldown()
        if resource.weekly_uses + 1 >= 1:
            await resource.set_weekly_cooldown()
        resource.weekly_uses += 1
        await resource.asave(update_fields=("weekly_uses",))
        await interaction.response.defer()
        balls = [
            x
            async for x in Ball.objects.filter(
                enabled=True,
                tradeable=True,
                rarity__range=(self.pack_settings.min_rarity_weekly, self.pack_settings.max_rarity_weekly),
            )
        ]
        ball = await self._get_random_countryball(balls)
        rarity = ball.rarity
        instance = await BallInstance.objects.acreate(
            player=player,
            ball=ball,
            health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
            attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
            server_id=interaction.guild_id,
        )
        embed = discord.Embed(title=f"🎁 You got {ball.country}!", color=settings.embed_colour)
        embed.description = f"📖 **Rarity:** {rarity}\n❤️ **Health:** {ball.health}\n⚔️ **Attack:** {ball.attack}\n"
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text="Come back next week for another pack!")
        with ThreadPoolExecutor() as pool:
            buffer = await interaction.client.loop.run_in_executor(pool, instance.draw_card)
        file = discord.File(buffer, "card.webp")
        embed.set_image(url="attachment://card.webp")
        await interaction.followup.send(embed=embed, file=file)

    @app_commands.command()
    async def shop(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Check available packs in the shop.
        """
        await self._show_shop(interaction, ItemModel.Section.SHOP)

    @app_commands.command()
    async def tiers(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Check the tier packs (Bronze, Silver, Gold...) available in the shop.
        """
        await self._show_shop(interaction, ItemModel.Section.TIERS)

    async def _show_shop(self, interaction: discord.Interaction["BallsDexBot"], section: ItemModel.Section):
        await interaction.response.defer(thinking=True)
        packs = [
            x
            async for x in ItemModel.objects.filter(section=section)
            .order_by("position", "prize")
            .prefetch_related("balls", "special")
        ]

        if not packs:
            await interaction.followup.send(f"{settings.bot_name} doesn't have any packs to buy here.")
            return

        source = ShopMenuSource(packs, self.bot)
        pages = ShopPages(source, interaction=interaction, compact=True)
        await pages.start()

    async def _get_random_countryball(self, countryballs: list[Ball]) -> Ball:
        if not countryballs:
            raise RuntimeError("No ball to spawn")
        rarities = [x.rarity for x in countryballs]
        cb = random.choices(population=countryballs, weights=rarities, k=1)[0]
        return cb
