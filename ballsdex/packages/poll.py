from typing import TYPE_CHECKING
import logging
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, button

from ballsdex.core.models import Ball
from ballsdex.core.utils.transformers import BallEnabledTransform
from ballsdex.settings import settings

from tortoise.exceptions import DoesNotExist

if TYPE_CHECKING:
  from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.poll")

def list_validator(multi_string):
    items = multi_string.split("|")
    if any(item.strip() == "" for item in items):
        raise ValueError("One or more items are empty or contain only whitespace.")
    return items

@app_commands.guilds(*settings.admin_guild_ids)
@app_commands.default_permissions(administrator=True)
class Poll(commands.GroupCog):
  """
  Poll builder command.
  """

  def __init__(self, bot: "BallsDexBot"):
    self.bot = bot

  @app_commands.command(name="create", description="Create a Discord poll!")
  @app_commands.describe(question="Question of the poll")
  @app_commands.choices(poll_type=[
        app_commands.Choice(name="Collectible", value="collectible"),
        app_commands.Choice(name="Custom", value="custom")
        ])
  @app_commands.describe(poll_type="Type of the poll")
  @app_commands.describe(duration="Duration of the poll (hours)")
  @app_commands.describe(allow_multiple="Whether to allow multiple select or not")
  @app_commands.describe(answers="Answers of the poll (Max 10). Each answer seperated with a colon (|).")
  @app_commands.checks.cooldown(1, 3, key=lambda i: i.user.id)
  @app_commands.checks.has_any_role(*settings.root_role_ids)
  async def create(
    self,
    interaction: discord.Interaction["BallsDexBot"],
    question: str,
    poll_type: app_commands.Choice[str],
    duration: int,
    allow_multiple: bool,
    answers: str
  ):
    try:
        formatted_array = list(list_validator(answers))
    except ValueError:
        await interaction.response.send_message("The answers format you provided is invalid. Please try again.", ephemeral=True)
        return
    if len(formatted_array) > 10:
        await interaction.response.send_message("You can't have more than 10 answers.", ephemeral=True)
        return
    poll = discord.Poll(
      question=question,
      duration=timedelta(hours=duration),
      multiple=allow_multiple
    )
    if poll_type.value == "collectible":
        for collectible in formatted_array:
            try: 
                collectible_object = await Ball.get(country=str(collectible))
            except DoesNotExist:
                await interaction.response.send_message(f'Collectible "{collectible}" does not exist.', ephemeral=True)
                return
            poll.add_answer(text=str(collectible_object.country), emoji=interaction.client.get_emoji(collectible_object.emoji_id))
        try:
            msg = await interaction.channel.send(poll=poll)
            timestamp = msg.poll.expires_at
            await interaction.response.send_message(f"Poll sent successfully! Poll will expire <t:{int(timestamp.timestamp())}:R> (<t:{int(timestamp.timestamp())}:f>).", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("Bot has missing permission to send polls.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message("Something went wrong while sending the poll.", ephemeral=True)
            log.error("Something went wrong.", exc_info=e)
          
    elif poll_type.value == "custom":
      await interaction.response.send_message("wip", ephemeral=True)

async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Poll(bot))
