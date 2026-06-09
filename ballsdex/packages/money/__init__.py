import logging
from typing import TYPE_CHECKING

from settings.models import settings

from .cog import Money

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.money")


async def setup(bot: "BallsDexBot"):
    if not settings.currency_enabled:
        log.warning("Disabling currency cog as it is not configured in the settings.")
        return
    assert settings.currency_name
    Money.__cog_group_name__ = settings.currency_name
    cog = Money(bot)
    await bot.add_cog(cog)
