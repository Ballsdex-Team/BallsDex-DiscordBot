from typing import TYPE_CHECKING

from ballsdex.packages.shop.cog import Shop

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Shop(bot))