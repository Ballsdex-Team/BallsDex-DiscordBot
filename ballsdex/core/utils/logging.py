import asyncio
import logging

import aiohttp
import discord

from ballsdex.settings import settings

log = logging.getLogger("ballsdex.core.utils.logging")


class WebhookLoggingHandler(logging.Handler):
    """
    Allows messages to be logged to a Discord webhook.
    """

    def __init__(self, webhook: str):
        super().__init__(logging.INFO)

        self.webhook = webhook

    async def send_to_webhook(self, message: str):
        async with aiohttp.ClientSession() as session:
            try:
                webhook = discord.Webhook.from_url(self.webhook, session=session)
                await webhook.send(message, username=f"{settings.bot_name} logging")
            except Exception:
                log.error("Failed to send message to webhook", exc_info=True)

    def emit(self, record):
        try:
            asyncio.create_task(self.send_to_webhook(self.format(record)))
        except Exception:
            self.handleError(record)


def webhook_logger(name: str | None = None, webhook_url: str | None = None) -> logging.Logger:
    """
    Returns a logger with a `WebhookLoggingHandler` handler.

    Parameters
    ----------
    name: str | None
        The name of the logger.
    webhook_url: str | None
        The webhook URL you want to log to. Defaults to `settings.webhook_url`.
    """
    new_logger = logging.getLogger(name)

    if webhook_url is None:
        webhook_url = settings.webhook_url

    if webhook_url is not None:
        new_logger.addHandler(WebhookLoggingHandler(webhook_url))

    return new_logger
