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
  async def toxicnuke(self, ctx: commands.Context, channel: discord.TextChannel = None, message_id: int = None):
      """
      Toxic nuke the user's message you replied (or a message ID) with reactions!
      """
      emoji_ids = [1381344524365725816, 1381344502241038518, 1381344484352196678, 1381344450487521330, 1381344407369809970, 1381344385064501349, 1381344365150212136, 1381344345550098442, 1381344327309066311, 1381344307260166304, 1381344287601725633, 1381344264507752558, 1381344233650262067]
      reactions = [await ctx.bot.fetch_application_emoji(eid) for eid in emoji_ids]
      if ctx.message.reference:
          msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
      if message_id:
          target_channel = channel or ctx.channel
          msg = await target_channel.fetch_message(message_id)
      for reaction in reactions:
          try:
              await msg.add_reaction(reaction)
          except discord.Forbidden:
              log.warning("Cannot add the reaction emoji. Permission denied.")
              break
          except discord.HTTPException:
              log.error("An error occurred while adding the reaction.", exc_info=True)
              break
          except discord.NotFound:
              log.warning("Cannot add the reaction emoji. Message not found.")
              break
      try:
          await ctx.message.delete()
      except discord.Forbidden:
          log.warning("Bot could not delete the message, permission denied.")

  @commands.command()
  @commands.is_owner()
  async def grombomb(self, ctx: commands.Context, user: str):
      """
      Sends a Grom Bomb!
      """
      target_user = None

      try:
          target_user = await commands.UserConverter().convert(ctx, user)
      except commands.BadArgument:
          pass

      if target_user is None:
        user_input_lower = user.lower()
        for member in ctx.guild.members:
            if member.name.lower() == user_input_lower or member.display_name.lower() == user_input_lower:
                user = member
                break
                
      if target_user is None:
          return

      await ctx.send(f"I have sent a Grom Bomb to {target_user.mention}'s location!")
      try:
          await ctx.message.delete()
      except discord.Forbidden:
          log.warning("Bot could not delete the message, permission denied.")
