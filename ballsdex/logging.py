import logging
import logging.handlers
from queue import Queue

from discord.utils import _ColourFormatter

log = logging.getLogger("ballsdex")


def init_logger(disable_rich: bool = False, debug: bool = False) -> logging.handlers.QueueListener:
    formatter = logging.Formatter(
        "[{asctime}] {levelname} {name}: {message}", datefmt="%Y-%m-%d %H:%M:%S", style="{"
    )
    rich_formatter = _ColourFormatter()

    # handlers
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    stream_handler.setFormatter(formatter if disable_rich else rich_formatter)

    # file handler
    file_handler = logging.handlers.RotatingFileHandler(
        "ballsdex.log", maxBytes=8**7, backupCount=8
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    queue = Queue(-1)
    queue_handler = logging.handlers.QueueHandler(queue)

    root = logging.getLogger()
    root.addHandler(queue_handler)
    root.setLevel(logging.INFO)
    log.setLevel(logging.DEBUG if debug else logging.INFO)

    queue_listener = logging.handlers.QueueListener(queue, stream_handler, file_handler)
    queue_listener.start()

    logging.getLogger("aiohttp").setLevel(logging.WARNING)  # don't log each prometheus call

    return queue_listener
