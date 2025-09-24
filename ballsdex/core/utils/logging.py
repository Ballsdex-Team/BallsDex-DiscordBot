import asyncio
import logging

import aiohttp
import discord

from ballsdex.settings import settings

log = logging.getLogger("ballsdex.core.utils.logging")
log.setLevel(logging.INFO)


class WebhookLogger(logging.Handler):
    """
    Logs messages via Discord webhooks.
    """

    def __init__(self, webhook: str):
        super().__init__(logging.INFO)

        self.session = aiohttp.ClientSession()
        self.webhook = discord.Webhook.from_url(webhook, session=self.session)

    async def send_to_webhook(self, message: str):
        try:
            await self.webhook.send(message)
        except Exception as error:
            print("Failed to send message to webhook")
            print(error)

    def emit(self, record):
        try:
            asyncio.create_task(self.send_to_webhook(self.format(record)))
        except Exception:
            self.handleError(record)

    def close(self):
        asyncio.create_task(self.session.close())


def init_logger():
    """
    Initiates a new `WebhookLogger` and adds it as a handler if `settings.webhook_url` is not None.
    """
    if not settings.webhook_url:
        return

    webhook_logger: WebhookLogger | None = None

    try:
        webhook_logger = WebhookLogger(settings.webhook_url)
    except Exception:
        log.error("An error occured while trying to initialize `WebhookLogger`", exc_info=True)
        return

    log.addHandler(webhook_logger)


async def log_action(message: str):
    """
    Logs an action through the `webhook_url` setting.
    Automatically logs the action to the console if webhook logging is not supported.

    Parameters
    ----------
    message: str
        The message you want to log.
    """
    log.propagate = len(log.handlers) == 0
    log.info(message)


init_logger()
