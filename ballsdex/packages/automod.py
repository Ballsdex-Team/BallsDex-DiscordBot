import logging
from datetime import datetime, timedelta

import discord
from discord.ext import commands

from ballsdex.settings import settings
from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.automod")


class AutoMod(commands.Cog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        BANNED_REACTIONS = [
            "🫃", "🫄", "🤰", "🤱", "🧑‍🍼", "👩‍🍼", "👨‍🍼",
            "🧑‍🦽", "👩‍🦽", "👨‍🦽", "🧑‍🦼", "👩‍🦼", "👨‍🦼",
            "🧑‍🦯", "👩‍🦯", "👨‍🦯", "🐕‍🦺", "🪚", "♿"
        ]

        if reaction.message.guild is None:
            return
        if reaction.message.guild.id not in settings.admin_guild_ids:
            return
        if user.bot:
            return
        if isinstance(user, discord.Member):
            user_role_ids = {role.id for role in user.roles}
            for role in user_role_ids:
                if role in settings.root_role_ids:
                    return
        if str(reaction.emoji) in BANNED_REACTIONS:
            try:
                await reaction.remove(user)
            except Exception:
                log.exception("An error occurred with Reaction AutoMod.", exc_info=True)


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(AutoMod(bot))
