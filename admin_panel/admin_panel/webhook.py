import logging
from typing import Literal, overload

import aiohttp
import discord
from discord.utils import MISSING

from ballsdex.settings import settings

log = logging.getLogger(__name__)


@overload
async def notify_admins(message: str = MISSING, *, wait: Literal[False]) -> None: ...  # noqa: E704
@overload  # noqa: E302
async def notify_admins(  # noqa: E704
    message: str = MISSING, *, wait: Literal[True] = True
) -> discord.WebhookMessage: ...


async def notify_admins(
    message: str = MISSING, *, wait: bool = True, **kwargs
) -> discord.WebhookMessage | None:
    """
    Send a message to the configured Discord webhook. Additional arguments are described here:
    https://discordpy.readthedocs.io/en/latest/api.html#discord.Webhook.send

    Set `wait` to `False` to ignore the resulting messsage, or failures to send it.
    """
    if not settings.webhook_url:
        log.warning(f"Discord webhook URL not configured, attempted to send: {message}")
        return
    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(settings.webhook_url, session=session)
        return await webhook.send(
            message, username="Ballsdex admin panel", wait=wait, **kwargs  # type: ignore
        )
