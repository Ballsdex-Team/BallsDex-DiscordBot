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

if TYPE_CHECKING:
  from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.poll")

def list_validator(multi_string):
    items = multi_string.split("|")
    if any(item.strip() == "" for item in items):
        raise ValueError("One or more items are empty or contain only whitespace.")
    return items

class Poll(commands.GroupCog):
  """
  Poll builder command.
  """

  def __init__(self, bot: "BallsDexBot"):
    self.bot = bot

  @app_commands.command(name="create", description="Create a Discord poll!")
  @app_commands.describe(question="Question of the poll")
  @app_commands.choices(type=[
        app_commands.Choice(name="Collectible", value="collectible"),
        app_commands.Choice(name="Custom", value="custom")
        ])
  @app_commands.describe(poll_type="Type of the poll")
  @app_commands.describe(duration="Duration of the poll (hours)")
  @app_commands.describe(allow_multiple="Whether to allow multiple select or not")
  @app_commands.describe(answers="Answers of the poll (Max 10). Each answer seperated with a colon (|).")
  @app_commands.checks.cooldown(1, 3, key=lambda i: i.user.id)
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
    if len(formatted_array) > 10:
        await interaction.response.send_message("You can't have more than 10 answers.", ephemeral=True)
    if poll_type == "collectible":
      
      
