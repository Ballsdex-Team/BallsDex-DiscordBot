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

        self.session = aiohttp.ClientSession()
        self.webhook = discord.Webhook.from_url(webhook, session=self.session)

    async def send_to_webhook(self, message: str):
        try:
            await self.webhook.send(message)
        except Exception:
            log.error("Failed to send message to webhook", exc_info=True)

    def emit(self, record):
        try:
            asyncio.create_task(self.send_to_webhook(self.format(record)))
        except Exception:
            self.handleError(record)

    def close(self):
        asyncio.create_task(self.session.close())


def webhook_logger(name: str | None = None) -> logging.Logger:
    """
    Creates a new logger and automatically adds `WebhookLoggingHandler` as a handler.
    """
    new_logger = logging.getLogger(name)

    if not settings.webhook_url:
        return new_logger

    try:
        new_logger.addHandler(WebhookLoggingHandler(settings.webhook_url))
    except Exception:
        log.warning("Failed to add `WebhookLoggingHandler` handler", exc_info=True)

    return new_logger
