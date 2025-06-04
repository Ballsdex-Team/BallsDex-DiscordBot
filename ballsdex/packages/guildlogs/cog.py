import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from ballsdex.core.bot import BallsDexBot
from ballsdex.settings import Settings
from ballsdex.core.utils.logging import log_action

log = logging.getLogger("ballsdex.packages.guildlogs")

class GuildLogs(commands.Cog):
  def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

  @commands.Cog.listener()
  async def on_guild_join(self, guild):
    try:
      await log_action(
              f"BrawlDex joined 
              self.bot,
            )
