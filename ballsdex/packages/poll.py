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
