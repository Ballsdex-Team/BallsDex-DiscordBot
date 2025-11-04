from typing import TYPE_CHECKING

from .cog import CountryBallsSpawner

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    cog = CountryBallsSpawner(bot)
    await bot.add_cog(cog)
    await cog.load_cache()
