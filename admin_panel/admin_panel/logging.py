"""
This file will contain various utility functions for setting up Ballsdex's logging.

You will find custom objects for the standard logging library and a custom logging setup for Django's startup.
"""

import logging
import logging.config
import logging.handlers
import os
import sys
import warnings
from collections import deque
from datetime import datetime
from typing import Self, Sequence, TypedDict, cast

import discord
from discord.ui import Container, TextDisplay
from discord.utils import format_dt


# BaseView calls asyncio.get_running_loop, which doesn't exist in this context
# this override is used to remove all async behavior to be used with SyncWebhook
class _SyncView(discord.ui.view.BaseView):
    def __init__(self, *, timeout: float | None = 180.0):
        self._children: list[discord.ui.Item[Self]] = self._init_children()  # pyright: ignore[reportIncompatibleVariableOverride]
        self.id: str = os.urandom(16).hex()
        self._cache_key: int | None = None
        self._total_children: int = len(tuple(self.walk_children()))

    def is_dispatchable(self) -> bool:
        return False


class LayoutView(discord.ui.LayoutView, _SyncView):
    pass


class WebhookParams(TypedDict, total=False):
    username: str
    avatar_url: str
    file: discord.File
    files: Sequence[discord.File]


class WebhookData(TypedDict, total=False):
    params: WebhookParams
    container: Container


class WebhookHandler(logging.Handler):
    """
    Log selected events to the configured Discord webhook.

    For a logging record to be sent to the Webhook, the following conditions must be met
    - The handler has been added to your logging handler
    - A Webhook URL has been configured
    - `extra={"webhook": True}` is present in your log call

    You can also specify additional parameters:
    ```py
    log.info(
        "My message",
        extra={
            "webhook": {
                "params": {"username": "Webhook name", "avatar_url": "...", "file": discord.File(...)},
                "container": discord.ui.Container(...),
            }
        },
    )
    ```
    """

    _accent_colours = {
        logging.DEBUG: discord.Colour.light_grey(),
        logging.INFO: discord.Colour.blue(),
        logging.WARNING: discord.Colour.orange(),
        logging.ERROR: discord.Colour.red(),
        logging.CRITICAL: discord.Colour.dark_red(),
    }

    def emit(self, record: logging.LogRecord):
        extra_data = cast(bool | WebhookData, getattr(record, "webhook", False))
        data: WebhookData
        if extra_data is False:
            return
        elif extra_data is True:
            data = {}
        else:
            data = extra_data

        try:
            from settings.models import settings
        except Exception:
            # settings not ready yet
            return

        if not settings.webhook_logging:
            warnings.warn("Webhook handler not configured.")
            return
        webhook = discord.SyncWebhook.from_url(settings.webhook_logging)
        if container := data.pop("container", None):
            if not container.accent_colour:
                container.accent_colour = self._accent_colours.get(record.levelno, None)
        else:
            container = Container(
                TextDisplay(
                    f"[{format_dt(datetime.fromtimestamp(record.created), style='S')}] "
                    f"{record.levelname}: {record.name}\n{record.message}"
                ),
                accent_colour=self._accent_colours.get(record.levelno, None),
            )
        view = LayoutView()
        view.add_item(container)
        webhook.send(view=view, wait=False, **data.pop("params", {}))


class RequireBot(logging.Filter):
    """
    This will disable loggers and handlers if the context isn't the Discord bot.
    """

    is_bot = "startbot" in sys.argv

    def filter(self, record: logging.LogRecord) -> bool | logging.LogRecord:
        return self.is_bot


class DequeHandler(logging.Handler):
    """
    This is similar to [logging.MemoryHandler][] or [logging.BufferingHandler][], except it's based on a bounded
    [deque][collections.deque].
    This means the handler will keep at most `maxlen` log records and discard old records as new one comes, without
    discarding the entire buffer. There is also no flushing mechanism.

    The usage of this handler is to display the recent logs from the application.
    """

    maxlen: int = 50

    def __init__(self, level: int | str = 0) -> None:
        super().__init__(level)
        self.deque: deque[logging.LogRecord] = deque(maxlen=self.maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        self.deque.append(record)


def setup_logging(config: dict):
    logging.config.dictConfig(config)
    handler = cast(logging.handlers.QueueHandler, logging.getHandlerByName("queue"))
    if handler.listener:
        handler.listener.start()
