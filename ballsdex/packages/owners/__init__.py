from typing import TYPE_CHECKING

from ballsdex.packages.owners.cog import Owners

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Owners(bot))