import logging
from typing import TYPE_CHECKING

from .commands import commands
from .groups import groups

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger(__name__)


def walk_commands():
    yield from groups
    yield from commands


async def setup(bot: "BallsDexBot"):
    balls_cog = bot.get_cog("Balls")
    if not balls_cog or not balls_cog.app_command:
        log.error("Failed to load balls extension commands.")
        return

    for command in walk_commands():
        balls_cog.app_command.add_command(command)


async def teardown(bot: "BallsDexBot"):
    balls_cog = bot.get_cog("Balls")

    if not balls_cog or not balls_cog.app_command:
        return

    for command in walk_commands():
        balls_cog.app_command.remove_command(command.name)
