import logging
import logging.config
import logging.handlers
from typing import cast


def setup_logging(config: dict):
    logging.config.dictConfig(config)
    handler = cast(logging.handlers.QueueHandler, logging.getHandlerByName("queue"))
    if handler.listener:
        handler.listener.start()
