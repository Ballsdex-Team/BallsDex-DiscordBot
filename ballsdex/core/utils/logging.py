import logging

import discord

from ballsdex.core.bot import BallsDexBot
from ballsdex.settings import settings

log = logging.getLogger("ballsdex.packages.admin.cog")


async def log_action(message: str, bot: BallsDexBot, console_log: bool = False):
    if settings.log_channel:
        channel = bot.get_channel(settings.log_channel)
        if not channel:
            log.warning(f"Channel {settings.log_channel} not found")
            return
        if not isinstance(channel, discord.TextChannel):
            log.warning(f"Channel {channel.name} is not a text channel")  # type: ignore
            return
        await channel.send(message)
    if console_log:
        log.info(message)
