from typing import TYPE_CHECKING
import logging

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

class PollCreatorView(View):
