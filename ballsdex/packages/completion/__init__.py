from typing import TYPE_CHECKING

from ballsdex.packages.completion.cog import Collection

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Collection(bot))
