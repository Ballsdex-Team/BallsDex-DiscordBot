from typing import TYPE_CHECKING

from ballsdex.packages.players.cog import Player

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Player(bot))
