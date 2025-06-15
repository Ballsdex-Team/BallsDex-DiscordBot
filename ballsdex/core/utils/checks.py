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

import os
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


async def _get_user_for_check(ctx: Context) -> "bool | User":
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
    if await ctx.bot.is_owner(ctx.author):
        return True
    user = await get_django_user(ctx.author)
    if not user or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return user


def _verify_existing_permissions(*perms: str):
    """
    Startup check that the permissions actually exist, to avoid typos.

    This is aimed to be used by decorators initializers, so this function is sync and runs in unsafe mode.

    Parameters
    ----------
    *perms: str
        A list of Django permissions

    Raises
    ------
    ValueError
        If one permission doesn't exist
    """
    if not perms:
        raise ValueError("You need to specify at least one permission")
    try:
        # Django will complain for using sync functions, but there's no easy way to do this in an async context
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

        for perm in perms:
            app, codename = perm.split(".")
            try:
                Permission.objects.get(codename=codename, content_type__app_label=app)
            except Permission.DoesNotExist as e:
                raise ValueError(f"Permission {perm} does not exist!") from e
    finally:
        # we don't want that to stay
        del os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"]


def is_staff():
    """
    Checks that the user is registered on Django and has the staff or superuser status.
    """

    async def check(ctx: Context) -> bool:
        user = await _get_user_for_check(ctx)
        if user is True or user is False:
            return user
        return user.is_staff

    return commands.check(check)


def is_superuser():
    """
    Checks that the user is registered on Django and has the superuser status.
    """

    async def check(ctx: Context) -> bool:
        user = await _get_user_for_check(ctx)
        if user is True or user is False:
            return user
        return user.is_superuser

    return commands.check(check)


def has_permissions(*perms: str):
    """
    Checks that the user is registered on Django and has the required permissions.
    """
    _verify_existing_permissions(*perms)

    async def check(ctx: Context) -> bool:
        user = await _get_user_for_check(ctx)
        if user is True or user is False:
            return user
        return await user.ahas_perms(perms)

    return commands.check(check)


def has_any_permissions(*perms: str):
    """
    Checks that the user is registered on Django and has any of the required permissions.
    """
    _verify_existing_permissions(*perms)

    async def check(ctx: Context) -> bool:
        user = await _get_user_for_check(ctx)
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
