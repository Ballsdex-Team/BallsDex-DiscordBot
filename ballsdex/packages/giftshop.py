import random
import logging

import discord
from discord.ext import commands

from ballsdex.core.models import Ball, BallInstance, Player, Regime
from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.giftshop")

async def setup(bot: "BallsDexBot"):
    await bot.add_cog(GiftShop(bot))
