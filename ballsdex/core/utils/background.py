"""
Run coroutines on the bot's event loop from anywhere, including synchronous code such as Django signal receivers
running in a worker thread.

Outside of the bot process (admin panel, management commands), nothing is scheduled: changes made from the admin
panel don't unlock achievements or send Discord messages.
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

log = logging.getLogger("ballsdex.core.utils.background")

_loop: asyncio.AbstractEventLoop | None = None
_tasks: set[asyncio.Task] = set()


def set_bot_loop(loop: asyncio.AbstractEventLoop):
    global _loop
    _loop = loop


def in_bot_process() -> bool:
    return _loop is not None


def _on_task_done(task: asyncio.Task):
    _tasks.discard(task)
    if not task.cancelled() and (exception := task.exception()):
        log.error("A background task failed", exc_info=exception)


def run_on_bot_loop(factory: Callable[[], Coroutine[Any, Any, Any]]):
    """
    Schedule the coroutine returned by `factory` on the bot's event loop. The factory is only called on the loop's
    thread, so the coroutine is never created if the bot isn't running.
    """
    loop = _loop
    if loop is None or loop.is_closed():
        return

    def start():
        task = loop.create_task(factory())
        _tasks.add(task)
        task.add_done_callback(_on_task_done)

    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is loop:
        start()
    else:
        loop.call_soon_threadsafe(start)
