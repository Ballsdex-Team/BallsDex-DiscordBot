import asyncio
import logging
import sys

from asgiref.sync import sync_to_async
from django.apps import AppConfig

log = logging.getLogger(__name__)


class SettingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "settings"

    def ready(self):
        if "makemigrations" in sys.argv or "migrate" in sys.argv or "collectstatic" in sys.argv:
            return

        from .models import load_settings

        try:
            # using uvicorn, the process will be in an async context and refuse to run sync db queries
            # so yes, we have to make a sync function async, and run it in a sync function
            task = asyncio.get_running_loop().create_task(sync_to_async(load_settings)())
            task.add_done_callback(lambda t: log.info("Settings read successfully."))
        except RuntimeError:
            # if the bot is running in a sync context
            load_settings()
