import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
import random
from tortoise import models, fields
import logging
import asyncio
logger = logging.getLogger(__name__)
from ballsdex.core.utils.transformers import (
    BallTransform,
    SpecialTransform,
)
from ballsdex.core.models import (
    Ball,
    balls,
    BallInstance,
    BlacklistedGuild,
    BlacklistedID,
    GuildConfig,
    Player,
    Trade,
    TradeObject,
    Special,
)
from ballsdex.settings import settings
from ballsdex.core.bot import BallsDexBot
import ballsdex.packages.config.components as Components
from collections import defaultdict

# Credits
# -------
# - crashtestalex
# - hippopotis
# - dot_zz
# -------

# Owners who can give packs
ownersid = {
    1327148447673094255,
    1300185879142469743
}

# Cooldowns
DAILY_COOLDOWN = timedelta(hours=24)

class Owners(commands.GroupCog, name="owners"):
    """
    A little simple daily pack!
    """

    def __init__(self, bot: BallsDexBot):
        self.bot = bot
        super().__init__()

    async def get_random_ball(self, player: Player) -> Ball | None:
        owned_ids = await BallInstance.filter(player=player).values_list("ball_id", flat=True)
        all_balls = await Ball.filter(rarity__gte=0.5, rarity__lte=30.0).all()

        if not all_balls:
            return None

        # Weight unowned balls higher
        weighted_choices = []
        for ball in all_balls:
            if ball.id in owned_ids:
                # Already owned — add fewer times (e.g. 1 weight)
                weighted_choices.append((ball, 2))
            else:
                # Not owned — higher chance (e.g. 5 weight)
                weighted_choices.append((ball, 2))

        # Flatten the weighted list
        choices = []
        for ball, weight in weighted_choices:
            choices.extend([ball] * weight)

        if not choices:
            return None

        return random.choice(choices)

    async def getdasigmaballmate(self, player: Player) -> Ball | None:
        owned_ids = await BallInstance.filter(player=player).values_list("ball_id", flat=True)
        all_balls = await Ball.filter(rarity__gte=0.01, rarity__lte=0.1).all() # same with the get_random_balls

        if not all_balls:
            return None

        # Weight unowned balls higher
        weighted_choices = []
        for ball in all_balls:
            if ball.id in owned_ids:
                # Already owned — add fewer times (e.g. 1 weight)
                weighted_choices.append((ball, 1))
            else:
                # Not owned — higher chance (e.g. 5 weight)
                weighted_choices.append((ball, 5))

        # Flatten the weighted list
        choices = []
        for ball, weight in weighted_choices:
            choices.extend([ball] * weight)

        if not choices:
            return None

        return random.choice(choices)
    
    @app_commands.command(name="daily", description="Claim your daily Footballer!")
    async def dailys(self, interaction: discord.Interaction[BallsDexBot]):
        user_id = str(interaction.user.id)
        username = interaction.user.name

        if interaction.user.id not in ownersid:
            await interaction.response.send_message(
                "❌ You’re not allowed to use this command.", ephemeral=True)
            return

        player, _ = await Player.get_or_create(discord_id=str(interaction.user.id))
        ball = await self.get_random_ball(player)

        if not ball:
            await interaction.response.send_message("No balls are available.", ephemeral=True)
            return

        instance = await BallInstance.create(
            ball=ball,
            player=player,
            attack_bonus=random.randint(-20, 20),
            health_bonus=random.randint(-20, 20),
        )

        emoji = self.bot.get_emoji(ball.emoji_id)
        color_choice = random.choice([
            discord.Color.from_rgb(229, 255, 0),
            discord.Color.from_rgb(255, 0, 0),
            discord.Color.from_rgb(0, 17, 255)
        ])

        embed = discord.Embed(
            title=f"{username}'s Daily Pack!",
            description=f"You received **{ball.country}**!",
            color=color_choice
        )
        embed.add_field(
            name=f"{emoji} **{ball.country}** (Rarity: {ball.rarity})",
            value=f"``💖 {instance.attack_bonus}`` ``⚽ {instance.health_bonus}``"
        )

        content, file, view = await instance.prepare_for_message(interaction)
        embed.set_image(url="attachment://" + file.filename)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text="Come back in 24 hours for your next claim! • Made by drift")

        await interaction.response.send_message(embed=embed, file=file, view=view)
        file.close()

    @app_commands.command(name="weekly", description="Claim your weekly Footballer!")
    async def weeklys(self, interaction: discord.Interaction[BallsDexBot]):
        user_id = str(interaction.user.id)
        username = interaction.user.name

        if interaction.user.id not in ownersid:
            await interaction.response.send_message(
                "❌ You’re not allowed to use this command.", ephemeral=True)
            return


        player, _ = await Player.get_or_create(discord_id=str(interaction.user.id))
        ball = await self.getdasigmaballmate(player)

        if not ball:
            await interaction.response.send_message("No footballers are available.", ephemeral=True)
            return

        instance = await BallInstance.create(
            ball=ball,
            player=player,
            attack_bonus=random.randint(-20, 20),
            health_bonus=random.randint(-20, 20),
        )

        # Walkout-style embed animation
        walkout_embed = discord.Embed(title="🎉 Weekly Pack Opening...", color=discord.Color.dark_gray())
        walkout_embed.set_footer(text="Come back in 7 days for your next claim! • Made by drift")
        await interaction.response.defer()
        msg = await interaction.followup.send(embed=walkout_embed)

        await asyncio.sleep(1.5)
        walkout_embed.description = f"✨ **Rarity:** `{ball.rarity}`"
        await msg.edit(embed=walkout_embed)

        await asyncio.sleep(1.5)
        regime_name = ball.cached_regime.name if ball.cached_regime else "Unknown"
        walkout_embed.description += f"\n💳 **Card:** **{regime_name}**"
        await msg.edit(embed=walkout_embed)

        await asyncio.sleep(1.5)
        walkout_embed.description += f"\n💖 **Health:** `{instance.health}`\n⚽ **Attack:** `{instance.attack}`"
        await msg.edit(embed=walkout_embed)

        await asyncio.sleep(1.5)
        emoji = self.bot.get_emoji(ball.emoji_id)
        walkout_embed.title = f"🎁 You got **{ball.country}**!"
        walkout_embed.color = discord.Color.from_rgb(229, 255, 0)  # You can randomize if you want
        walkout_embed.add_field(
            name=f"{emoji} **{ball.country}**",
            value=f"Rarity: `{ball.rarity}`\n💖 `{instance.health}` ⚽ `{instance.attack}`"
        )

        content, file, view = await instance.prepare_for_message(interaction)
        walkout_embed.set_image(url="attachment://" + file.filename)
        walkout_embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

        await msg.edit(embed=walkout_embed, attachments=[file], view=view)
        file.close()

    @app_commands.command(name="store", description="View the exclusive store packs.")
    async def store(self, interaction: discord.Interaction):
        # Check if user is allowed
        if interaction.user.id not in ownersid:
            await interaction.response.send_message("🚫 You do not have access to the store.", ephemeral=True)
            return

        loading_msg = await interaction.response.send_message("🔄 Loading store...", ephemeral=False)
        await asyncio.sleep(1.5)

        embed = discord.Embed(
            title="🛍️  Welcome to the Pack Store!",
            description="Here are the available packs you can choose from: (EDUCATIONAL PURPOSES ALL FAKE)",
            color=discord.Color.purple()
        )
        embed.add_field(name="🎁 Classic Pack", value="Contains 1 random ball\n`/buy classic`", inline=False)
        embed.add_field(name="🔥 Elite Pack", value="Guaranteed 8.0+ stats\n`/buy elite`", inline=False)
        embed.add_field(name="💎 Legendary Pack", value="Rare or higher only\n`/buy legendary`", inline=False)
        embed.add_field(name="🧪 Mystery Pack", value="??? (secret contents!)\n`/buy mystery`", inline=False)
        embed.set_footer(text="Use /buy <pack> to purchase your pack.")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        await interaction.edit_original_response(content=None, embed=embed)
