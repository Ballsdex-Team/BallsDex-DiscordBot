from typing import TYPE_CHECKING

from ballsdex.packages.powerlevel.cog import PowerLevel

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

async def setup(bot: "BallsDexBot"):
    await bot.add_cog(PowerLevel(bot))
