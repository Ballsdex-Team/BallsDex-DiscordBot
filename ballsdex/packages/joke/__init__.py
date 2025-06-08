from typing import TYPE_CHECKING

from ballsdex.packages.joke.cog import Joke

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Joke(bot))
