from typing import TYPE_CHECKING

from ballsdex.packages.completion.cog import Completion

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Completion(bot))
