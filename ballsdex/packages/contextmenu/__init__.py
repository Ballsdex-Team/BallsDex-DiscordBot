from typing import TYPE_CHECKING

from ballsdex.packages.contextmenu.cog import ContextMenuCommands

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(ContextMenuCommands(bot))
