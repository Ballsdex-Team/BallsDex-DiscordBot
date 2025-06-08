import random
import logging
import asyncio

import discord
from discord.ext import commands

from ballsdex.settings import settings
from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.joke")


ALLOWED_GUILDS = []
for guild_id in settings.admin_guild_ids:
    ALLOWED_GUILDS.append(guild_id)
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
      toothpastes = ["mango", "strawberry", "mint", "chocolate", "amongus", "discord", "yippee", "brawl stars", "cement", "dynamike song tutorial"]
      picked_toothpaste = random.choice(toothpastes)
      await ctx.send(f"colgate {picked_toothpaste} toothpaste")
      try:
          await ctx.message.delete()
      except discord.Forbidden:
          log.warning("Bot could not delete the message, permission denied.")

  @colgate.error
  async def colgate_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            return

  @commands.command()
  @commands.cooldown(1, 60, commands.BucketType.user)
  async def jfbd(self, ctx: commands.Context):
      """
      Justice for BrawlDex!
      """
      emoji_1 = ctx.bot.get_emoji(1364595411213619200)
      emoji_2 = ctx.bot.get_emoji(1368258491340427396)
      messages = ["#justiceforbrawldex", "Justice for BrawlDex!", emoji_1, emoji_2]
      picked_message = random.choice(messages)
      await ctx.send(picked_message)
      try:
          await ctx.message.delete()
      except discord.Forbidden:
          log.warning("Bot could not delete the message, permission denied.")

  @jfbd.error
  async def jfbd_error(self, ctx, error):
      if isinstance(error, commands.CommandOnCooldown):
          return
          
  @commands.command()
  @commands.is_owner()
