from typing import TYPE_CHECKING, Callable

import discord
from discord import app_commands
from discord.ext import commands

from .django import get_django_user

if TYPE_CHECKING:
    from discord.ext.commands._types import Check as CommandsCheck
    from django.contrib.auth.models import User

    from ballsdex.core.bot import BallsDexBot

type Context = commands.Context["BallsDexBot"]


async def _get_user_for_check(ctx: Context) -> "bool | User":
    if await ctx.bot.is_owner(ctx.author):
        return True
    user = await get_django_user(ctx.author)
    if not user:
        return False
    if user.is_superuser:
        return True
    return user


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

    async def check(ctx: Context) -> bool:
        user = await _get_user_for_check(ctx)
        if user is True or user is False:
            return user
        return await user.ahas_perms(perms)

    return commands.check(check)


def app_check(func: Callable[[], "CommandsCheck[Context]"]):
    """
    Converts a commands check decorator to an app command compatible check decorator.

    Example
    -------
        from ballsdex.core.utils.checks import app_check, is_staff

        @app_commands.command()
        @app_check(is_staff)
        async def command(interaction):
            ...
    """

    async def check(interaction: discord.Interaction["BallsDexBot"]):
        return await func().predicate(await commands.Context.from_interaction(interaction))

    return app_commands.check(check)
