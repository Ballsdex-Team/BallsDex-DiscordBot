from typing import TYPE_CHECKING

from ballsdex.packages.custom.cog import Custom

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Custom(bot))