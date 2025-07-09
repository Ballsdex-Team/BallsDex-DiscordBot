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

class PollObject:
  def __init__(self):
    self.type = "custom"
    self.question = ""
    self.duration = 1
    self.allow_multiple = False
    self.answers = []

class PollBuilderView(View):
    def __init__(self, poll: PollObject, author: discord.User):
        super().__init__(timeout=600)
        self.poll = poll
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    @button(label="Set Question", style=discord.ButtonStyle.primary, emoji=❔)
    async def set_question(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(QuestionModal(self.poll))

    @button(label="Set Duration", style=discord.ButtonStyle.secondary, emoji=⏲)
    async def set_duration(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(DurationModal(self.poll))

    @button(label="Toggle Multi Select", style=discord.ButtonStyle.secondary, emoji=🔢)
    async def toggle_multi(self, interaction: discord.Interaction, button: Button):
        self.poll.allow_multiple = not self.poll.allow_multiple
        await interaction.response.send_message(f"Toggled to **{"Enabled" if self.poll.allow_multiple == True else "Disabled"}**.", ephemeral=True)

    @button(label="Add Answer", style=discord.ButtonStyle.success, emoji=⚙)
    async def add_option(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.poll.options) >= 10:
            await interaction.response.send_message("You've reached the 10-option limit.", ephemeral=True)
        else:
            await interaction.response.send_modal(OptionModal(self.poll))

    @discord.ui.button(label="Finish", style=discord.ButtonStyle.green)
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        summary = (
            f"**Question:** {self.poll.question}\n"
            f"**Duration:** {self.poll.duration} hour(s)\n"
            f"**Anonymous:** {self.poll.anonymous}\n"
            f"**Options:**\n"
        )
        for i, opt in enumerate(self.poll.options, 1):
            summary += f"{i}. {opt.get('emoji', '')} {opt['text']}\n"

        await interaction.response.send_message(summary or "No poll data", ephemeral=True)
        self.stop()
