import logging
from typing import TYPE_CHECKING

from discord import app_commands

from settings.models import settings

from .commands import commands
from .groups import groups

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger(__name__)


def walk_commands():
    yield from groups
    yield from commands


async def setup(bot: "BallsDexBot"):
    group = bot.tree.get_command(settings.balls_slash_name)
    if not group or not isinstance(group, app_commands.Group):
        log.error("Failed to load balls extension commands.")
        return

    for command in walk_commands():
        group.add_command(command)


async def teardown(bot: "BallsDexBot"):
    group = bot.tree.get_command(settings.balls_slash_name)

    if not group or not isinstance(group, app_commands.Group):
        return

    for command in walk_commands():
        group.remove_command(command.name)
