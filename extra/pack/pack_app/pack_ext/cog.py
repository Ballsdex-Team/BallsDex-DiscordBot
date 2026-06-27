import random
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import TYPE_CHECKING

import discord
from currency_app.models import CurrencySettings, MoneyInstance
from currency_app.models import Item as ItemModel
from discord import app_commands
from discord.ext import commands
from discord.utils import format_dt
from pack_models.models import PackResource, PackSettings

from ballsdex.settings import settings
from bd_models.models import Ball, BallInstance, Player

from .components import ShopMenuSource, ShopPages

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


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

    @app_commands.command(name="daily")
    async def daily(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Claim your daily pack! (3 uses)
        """
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        resource, _ = await PackResource.objects.aget_or_create(player=player)
        if await resource.is_daily_on_cooldown():
            await interaction.response.send_message(
                f"You've used all daily packs. "
                f"Come back {format_dt(resource.daily_cooldown + timedelta(days=1), style='R')}!",  # type: ignore
                ephemeral=True,
            )
            return
        if not self.pack_settings.min_rarity_daily or not self.pack_settings.max_rarity_daily:
            await interaction.response.send_message(
                "Daily packs are not configured. Contact support if this persists.", ephemeral=True
            )
            return

        if resource.daily_cooldown is not None:
            await resource.remove_daily_cooldown()
        if resource.daily_uses + 1 >= 3:
            await resource.set_daily_cooldown()
        resource.daily_uses += 1
        await resource.asave(update_fields=("daily_uses",))
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
        )
        embed = discord.Embed(title=f"🎁 You got {ball.country}!", color=discord.Color.gold())
        embed.description = f"📖 **Rarity:** {rarity}\n❤️ **Health:** {ball.health}\n⚔️ **Attack:** {ball.attack}\n"
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        footer_text = (
            f"Uses: {resource.daily_uses}/3. Come back tomorrow."
            if resource.daily_uses >= 3
            else f"Uses: {resource.daily_uses}/3."
        )
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
        )
        embed = discord.Embed(title=f"🎁 You got {ball.country}!", color=discord.Color.gold())
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
        await interaction.response.defer(thinking=True)
        currency_settings = await CurrencySettings.aload()
        packs = [x async for x in ItemModel.objects.order_by("prize").prefetch_related("balls", "special").all()]

        if not packs:
            await interaction.followup.send(f"{settings.bot_name} doesn't have any packs to buy.")
            return

        source = ShopMenuSource(packs, self.bot, currency_settings)
        pages = ShopPages(source, interaction=interaction, compact=True)
        await pages.start()

    @app_commands.command()
    @app_commands.checks.cooldown(1, 86400, key=lambda i: i.user.id)
    async def coin_daily(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Claim your daily payment.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        currency_settings = await CurrencySettings.aload()
        currency_emoji = self.bot.get_emoji(currency_settings.emoji_id) if currency_settings.emoji_id else ""
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        instance, _ = await MoneyInstance.objects.aget_or_create(player=player)

        instance.amount += 1500
        await instance.asave(update_fields=("amount",))

        await interaction.followup.send(
            "You've claimed  "
            f"**{currency_emoji} 1,500 {currency_settings.display_name(1500)}**! "
            f"Now you have **{instance.amount:,}**. Come back tomorrow!"
        )

    @app_commands.command()
    async def coin_balance(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Check your actual coin balance.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        currency_settings = await CurrencySettings.aload()
        currency_emoji = self.bot.get_emoji(currency_settings.emoji_id) if currency_settings.emoji_id else ""
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        instance, _ = await MoneyInstance.objects.aget_or_create(player=player)

        await interaction.followup.send(
            f"You have **{currency_emoji} {instance.amount:,} {currency_settings.display_name(instance.amount)}**"
        )
        return

    async def _get_random_countryball(self, countryballs: list[Ball]) -> Ball:
        if not countryballs:
            raise RuntimeError("No ball to spawn")
        rarities = [x.rarity for x in countryballs]
        cb = random.choices(population=countryballs, weights=rarities, k=1)[0]
        return cb
