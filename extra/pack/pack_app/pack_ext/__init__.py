from typing import TYPE_CHECKING

from .cog import Pack

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    from pack_models.models import PackSettings

    settings = await PackSettings.aload()
    await bot.add_cog(Pack(bot, settings))
