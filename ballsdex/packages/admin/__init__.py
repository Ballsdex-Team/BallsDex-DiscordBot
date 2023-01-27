from typing import TYPE_CHECKING

from ballsdex.packages.admin.cog import Admin

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Admin(bot))
