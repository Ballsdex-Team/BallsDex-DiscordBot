from typing import TYPE_CHECKING

from .. import models
from .cog import Achievement

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    models._BOT = bot
    await bot.add_cog(Achievement(bot))
