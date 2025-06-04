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
    join_time = datetime.now(timezone.utc)
    timestamp = f"<t:{int(join_time.timestamp())}:f>"
    try:
        await log_action(
              f"BrawlDex joined {guild.name} {timestamp}. "
              f"(ID: {guild.id})"
              self.bot,
            )
    except Exception as e:
         log.error(f"Failed to send the join log {e}")
