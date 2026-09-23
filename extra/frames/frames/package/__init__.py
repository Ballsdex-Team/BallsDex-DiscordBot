from typing import TYPE_CHECKING

from .cog import FrameCommands, FramesCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot") -> None:
    await bot.add_cog(FramesCog(bot))
    await bot.add_cog(FrameCommands(bot))
