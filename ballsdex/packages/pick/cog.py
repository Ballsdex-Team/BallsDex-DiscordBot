import asyncio
import logging
import random
import re
import time
from pathlib import Path
from typing import cast, Union

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.utils import format_dt
from tortoise.exceptions import BaseORMException, DoesNotExist

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.models import Ball, BallInstance, Player, Special, Trade, TradeObject, balls
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.logging import log_action
from ballsdex.core.utils.transformers import (
    BallTransform,
    EconomyTransform,
    RegimeTransform,
    SpecialTransform,
)
from ballsdex.packages.countryballs.countryball import CountryBall
from ballsdex.settings import settings

log = logging.getLogger("ballsdex.packages.pick")
FILENAME_RE = re.compile(r"^(.+)(\.\S+)$")

class PickView(discord.ui.View):
    def __init__(self, balls, user: Union[discord.User, discord.Member], bot: "BallsDexBot", timeout=60):
        super().__init__(timeout=timeout)
        self.value = None
        self.user = user
        self.balls = balls
        self.bot = bot

        for i in range(3):
            self.add_item(self.CountryballButton(index=i))

    class CountryballButton(discord.ui.Button):
        def __init__(self, index):
            super().__init__(label=str(index + 1), style=discord.ButtonStyle.primary)
            self.index = index

        async def callback(self, interaction: discord.Interaction):
            view = cast(PickView, self.view)
            if interaction.user != view.user:
                await interaction.response.send_message("This is not your pick!", ephemeral=True)
                return

            chosen_ball = view.balls[self.index]
            chosen_emj = view.bot.get_emoji(chosen_ball.model.emoji_id)
            view.value = chosen_ball

            chosen_ball_instance = await BallInstance.create(
                ball=chosen_ball.model,
                player= await Player.get(discord_id=view.user.id),
                attack_bonus=random.randint(-20, 20),
                health_bonus=random.randint(-20, 20),
                special=None
            )

            await interaction.response.defer()
            for item in view.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

            if interaction.message:
                await interaction.message.edit(view=view)

            await interaction.followup.send(
                    f"You have picked {chosen_emj} **{chosen_ball_instance.ball.country}**!"
            )

            view.stop()

class Pick(commands.Cog):
    """
    Pick command.
    """
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot 

    @app_commands.command()
    @app_commands.checks.cooldown(1, 604800, key=lambda i: i.user.id)
    async def pick(self, interaction: discord.Interaction):
        """
        Choose from 3 different ______s - by CrashTestAlex
        """
        UserID = str(interaction.user.id)

        ball1 = await CountryBall.get_random(min_rarity=0.6, max_rarity=5.0)
        ball2 = await CountryBall.get_random(min_rarity=0.6, max_rarity=5.0)
        ball3 = await CountryBall.get_random(min_rarity=0.6, max_rarity=5.0)
        countryballs = [ball1, ball2, ball3]
        bot = cast(BallsDexBot, interaction.client)

        view = PickView([ball1, ball2, ball3], interaction.user, bot)

        emoji1 = bot.get_emoji(ball1.model.emoji_id)
        emoji2 = bot.get_emoji(ball2.model.emoji_id)
        emoji3 = bot.get_emoji(ball3.model.emoji_id)

        embed = discord.Embed(
            title=f"Pick a {settings.collectible_name}",
            description="\n".join([
                f"**1.** {emoji1} **{ball1.name}** (Rarity: {ball1.rarity})",
                f"**2.** {emoji2} **{ball2.name}** (Rarity: {ball2.rarity})",
                f"**3.** {emoji3} **{ball3.name}** (Rarity: {ball3.rarity})"
            ]),
            color=discord.Color.blurple()
        )

        await interaction.response.send_message(embed=embed, view=view)

        await view.wait()

        if view.value is None:
            await interaction.followup.send(f"You didn't pick a {settings.collectible_name} in time! Too bad...", ephemeral=True)
