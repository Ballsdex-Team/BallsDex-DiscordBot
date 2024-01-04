from typing import TYPE_CHECKING

from ballsdex.packages.gapacks.cog import gaPacks #Import Class

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(gaPacks(bot))
