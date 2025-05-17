from typing import TYPE_CHECKING

from ballsdex.packages.starrdrop.cog import StarrDrop

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(StarrDrop(bot))
