from ballsdex.core.bot import BallsDexBot
from ballsdex.settings import settings

import logging

log = logging.getLogger("ballsdex.packages.admin.cog")


async def log_action(message: str, bot: BallsDexBot, console_log: bool = False):
    if settings.log_channel:
        channel = bot.get_channel(settings.log_channel)
        if channel:
            await channel.send(message)
    if console_log:
        log.info(message)
