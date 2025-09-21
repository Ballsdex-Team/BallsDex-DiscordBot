from typing import TYPE_CHECKING

from ballsdex.packages.boss.cog import Boss

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Boss(bot))
