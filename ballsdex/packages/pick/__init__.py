from typing import TYPE_CHECKING

from ballsdex.packages.pick.cog import Pick

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    cog = Pick(bot)
    await bot.add_cog(cog)
