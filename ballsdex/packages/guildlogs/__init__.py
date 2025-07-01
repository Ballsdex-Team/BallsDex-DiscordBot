from typing import TYPE_CHECKING
from datetime import datetime

import discord

from ballsdex.packages.guildlogs.cog import GuildLogs

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    channel = bot.get_channel(1295411468765888592)
    embed = discord.Embed(
        description=f":green_circle: {bot.user.mention} is now online!",
        color=discord.Colour.green(),
        timestamp=datetime.utcnow()
    )
    await bot.add_cog(GuildLogs(bot))
    await channel.send(embed=embed)

async def teardown(bot: "BallsDexBot"):
    channel = bot.get_channel(1295411468765888592)
    embed = discord.Embed(
        description=f":red_circle: {bot.user.mention} is now offline!",
        color=discord.Colour.red(),
        timestamp=datetime.utcnow()
    )
    await channel.send(embed=embed)
