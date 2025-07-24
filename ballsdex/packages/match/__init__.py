from typing import TYPE_CHECKING

from ballsdex.packages.match.cog import Match

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Match(bot))
