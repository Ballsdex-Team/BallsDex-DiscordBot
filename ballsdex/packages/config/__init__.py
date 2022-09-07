from typing import TYPE_CHECKING

from ballsdex.packages.config.cog import Config

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Config(bot))
