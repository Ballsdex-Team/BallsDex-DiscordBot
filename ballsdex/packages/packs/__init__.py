from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    from .cog import Packs
    
    await bot.add_cog(Packs(bot))

