import discord, random
from discord import app_commands
from discord.ext import commands
from ballsdex.settings import settings
from ballsdex.core.models import Ball, BallInstance, Player, balls, Special

class CustomWeekly(commands.GroupCog, group_name="weekly"):
