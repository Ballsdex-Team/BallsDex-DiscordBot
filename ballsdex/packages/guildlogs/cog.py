import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from ballsdex.core.bot import BallsDexBot
from ballsdex.settings import settings

log = logging.getLogger("ballsdex.packages.guildlogs")

class GuildLogs(commands.Cog):
  def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

  @commands.Cog.listener()
  async def on_guild_join(self, guild):
    join_time = datetime.now(timezone.utc)
    timestamp = f"<t:{int(join_time.timestamp())}:R>"
    channel = self.bot.get_channel(settings.log_channel)
    await channel.send(f"BrawlDex joined {guild.name} {timestamp}. (ID: {guild.id})\nMembers: {guild.member_count}\nOwner ID: {guild.owner_id}\nCurrent Server Count: {len(self.bot.guilds)}")

  @commands.Cog.listener()
  async def on_guild_remove(self, guild):
    leave_time = datetime.now(timezone.utc)
    timestamp = f"<t:{int(leave_time.timestamp())}:R>"
    channel = self.bot.get_channel(settings.log_channel)
    await channel.send(f"BrawlDex left {guild.name} {timestamp}. (ID: {guild.id})\nMembers: {guild.member_count}\nOwner ID: {guild.owner_id}\nCurrent Server Count: {len(self.bot.guilds)}")
