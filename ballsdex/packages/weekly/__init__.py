from typing import TYPE_CHECKING

from ballsdex.packages.weekly.cog import CustomWeekly

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

async def setup(bot: "BallsDexBot"):
    await bot.add_cog(CustomWeekly(bot))
