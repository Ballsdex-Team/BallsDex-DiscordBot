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
    embed = discord.Embed(
      description=f"BrawlDex joined {guild.name} {timestamp}.\n\n**Server Details**\nID: {guild.id}\nMember Count: {guild.member_count}\nOwner: <@{guild.owner_id}> (ID: {guild.owner_id})",
      color=discord.Colour.green(),
      timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Current Server Count: {len(self.bot.guilds)}")
    embed.set_thumbnail(url=self.bot.user.display_avatar.url)
    try:
        await channel.send(embed=embed)
    except Exception:
        log.error("An error occurred while sending the guild join log.", exc_info=True)
                  
  @commands.Cog.listener()
  async def on_guild_remove(self, guild):
    leave_time = datetime.now(timezone.utc)
    timestamp = f"<t:{int(leave_time.timestamp())}:R>"
    channel = self.bot.get_channel(settings.log_channel)
    embed = discord.Embed(
      description=f"BrawlDex left {guild.name} {timestamp}.\n\n**Server Details**\nID: {guild.id}\nMember Count: {guild.member_count}\nOwner: <@{guild.owner_id}> (ID: {guild.owner_id})",
      color=discord.Colour.red(),
      timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Current Server Count: {len(self.bot.guilds)}")
    embed.set_thumbnail(url=self.bot.user.display_avatar.url)
    try:
        await channel.send(embed=embed)
    except Exception:
        log.error("An error occurred while sending the guild leave log.", exc_info=True)
