"""
Internal checks for commands. To be used as decorators on commands.

Multiple decorators can be chained, in which case all conditions must pass.

These checks can only be used on text and hybrid commands. To use them on application commands, use the [`app_check`][]
wrapper.

See also
--------
    - [`discord.py` general documentation on checks](https://discordpy.readthedocs.io/en/latest/ext/commands/commands.html#checks)
    - [List of built-in `discord.py` checks](https://discordpy.readthedocs.io/en/latest/ext/commands/api.html#checks)
"""

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from django.contrib.auth.models import Permission

from .django import get_django_user

if TYPE_CHECKING:
    from discord.ext.commands._types import Check as CommandsCheck
    from django.contrib.auth.models import User

    from ballsdex.core.bot import BallsDexBot

type Context = commands.Context["BallsDexBot"]

log = logging.getLogger(__name__)

# used to check during startup that the permissions passed to decorators actually exist
registered_perms: set[str] = set()


# check that all passed permissions actually exist, otherwise emit a warning
# this has to be checked in a separate function because decorators are synchronous and cannot access the database
async def check_perms():
    for perm in registered_perms:
        try:
            app_label, codename = perm.split(".")
        except ValueError:
            log.warning(f"Permission name should be in the form app_label.permission_codename, not {perm}.")
            continue

        if not await Permission.objects.filter(codename=codename, content_type__app_label=app_label).aexists():
            log.warning(f"Permission {perm} does not exist and will be ignored.")
    registered_perms.clear()


async def get_user_for_check(bot: "BallsDexBot", user: discord.abc.User) -> "bool | User":
    """
    Get a Django user ready and performs common permission checking.

    Paremeters
    ----------
    ctx: commands.Context[BallsDexBot]
        The context of the invoked command

    Returns
    -------
    bool | django.contrib.auth.models.User
        - [`False`][] if the user should not be granted anything (not found or inactive)
        - [`True`][] if the user should immediately be granted permissions (superuser or bot owner)
        - [`User`][django.contrib.auth.models.User] if the user was found but should be inspected further
    """
    if await bot.is_owner(user):
        return True
    dj_user = await get_django_user(user)
    if not dj_user or not dj_user.is_active:
        return False
    if dj_user.is_superuser:
        return True
    return dj_user


def is_staff():
    """
    Checks that the user is registered on Django and has the staff or superuser status.
    """

    async def check(ctx: Context) -> bool:
        user = await get_user_for_check(ctx.bot, ctx.author)
        if user is True or user is False:
            return user
        return user.is_staff

    return commands.check(check)


def is_superuser():
    """
    Checks that the user is registered on Django and has the superuser status.
    """

    async def check(ctx: Context) -> bool:
        user = await get_user_for_check(ctx.bot, ctx.author)
        if user is True or user is False:
            return user
        return user.is_superuser

    return commands.check(check)


def has_permissions(*perms: str):
    """
    Checks that the user is registered on Django and has the required permissions.
    """
    registered_perms.update(perms)

    async def check(ctx: Context) -> bool:
        user = await get_user_for_check(ctx.bot, ctx.author)
        if user is True or user is False:
            return user
        return await user.ahas_perms(perms)

    return commands.check(check)


def has_any_permissions(*perms: str):
    """
    Checks that the user is registered on Django and has any of the required permissions.
    """
    registered_perms.update(*perms)

    async def check(ctx: Context) -> bool:
        user = await get_user_for_check(ctx.bot, ctx.author)
        if user is True or user is False:
            return user
        for perm in perms:
            if await user.ahas_perms(perm):
                return True
        return False

    return commands.check(check)


def app_check(func: "CommandsCheck[Context]"):
    """
    Converts a commands check decorator to an app command compatible check decorator.

    Example
    -------
        from ballsdex.core.utils.checks import app_check, is_staff

        @app_commands.command()
        @app_check(is_staff())
        async def command(interaction):
            ...
    """

    async def check(interaction: discord.Interaction["BallsDexBot"]):
        return await func.predicate(await commands.Context.from_interaction(interaction))

    return app_commands.check(check)
