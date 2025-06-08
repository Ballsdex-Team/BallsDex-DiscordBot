import random
import logging
import asyncio

import discord
from discord.ext import commands

from ballsdex.settings import settings
from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.joke")


*ALLOWED_GUILDS = settings.admin_guild_ids
def is_in_allowed_guild():
    async def predicate(ctx):
        return ctx.guild and ctx.guild.id in ALLOWED_GUILDS
    return commands.check(predicate)

@commands.check(is_in_allowed_guild())
class Joke(commands.Cog):
  """ 
  Funny joke commands.
  """
  
  def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

  @commands.command()
  @commands.cooldown(1, 300, commands.BucketType.user)
  async def colgate(self, ctx: commands.Context):
      """
      What Colgate toothpaste will you get today? Try your luck!
      """
      toothpastes = [
