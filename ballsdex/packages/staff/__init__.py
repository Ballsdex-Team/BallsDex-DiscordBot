from typing import TYPE_CHECKING

from ballsdex.packages.staff.cog import Staff

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Staff(bot))
