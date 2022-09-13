from typing import TYPE_CHECKING

from ballsdex.packages.info.cog import Info

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Info(bot))
