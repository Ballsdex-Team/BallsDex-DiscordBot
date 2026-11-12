import logging

import discord
from asgiref.sync import sync_to_async
from discord.ext import commands
from django.db import connection

from knydex.core.bot import knyDexBot
from knydex.core.utils import checks
from knydex.core.utils.buttons import ConfirmChoiceView
from kny_models.models import Player
from settings.models import settings
from settings.utils import format_currency

log = logging.getLogger(__name__)


@commands.hybrid_group()
@checks.has_permissions("kny_models.view_player")
async def yen(ctx: commands.Context[knyDexBot]):
    """
    Currency management tools
    """
    await ctx.send_help(ctx.command)


@money.command()
@checks.has_permissions("kny_models.view_player")
async def balance(ctx: commands.Context[knyDexBot], user: discord.User):
    """
    Show the balance of the user provided

    Parameters
    ----------
    user: discord.User
        The user you want to get information about.
    """
    player = await Player.objects.aget_or_none(discord_id=user.id)
    if not player:
        await ctx.send(f"This user does not have a {settings.bot_name} account.", ephemeral=True)
        return

    await ctx.send(
        f"{user.mention} currently has {format_currency(player.yen, shortened=False, bot=ctx.bot)}.", ephemeral=True
    )


@yen.command()
@checks.has_permissions("kny_models.change_player")
async def add(ctx: commands.Context[knyDexBot], user: discord.User, amount: int):
    """
    Add yen to the user provided

    Parameters
    ----------
    user: discord.User
        The user you want to add yen to.
    amount: int
        The amount of yen to add.
    """
    player = await Player.objects.aget_or_none(discord_id=user.id)
    if not player:
        await ctx.send(f"This user does not have a {settings.bot_name} account.", ephemeral=True)
        return

    if amount <= 0:
        await ctx.send("The amount must be greater than zero.", ephemeral=True)
        return

    await player.add_yen(amount)
    formatted = format_currency(amount, shortened=False, bot=ctx.bot)
    await ctx.send(f"Added {formatted} to {user.mention}.", ephemeral=True)
    log.info(f"{ctx.author} ({ctx.author.id}) added {formatted} to {user} ({user.id})", extra={"webhook": True})


@yen.command()
@checks.has_permissions("kny_models.change_player")
async def remove(ctx: commands.Context[knyDexBot], user: discord.User, amount: int):
    """
    Remove yen from the user provided

    Parameters
    ----------
    user: discord.User
        The user you want to remove yen from.
    amount: int
        The amount of yen to remove.
    """
    player = await Player.objects.aget_or_none(discord_id=user.id)
    if not player:
        await ctx.send(f"This user does not have a {settings.bot_name} account.", ephemeral=True)
        return

    if amount <= 0:
        await ctx.send("The amount must be greater than zero.", ephemeral=True)
        return
    try:
        await player.remove_yen(amount)
    except ValueError:
        await ctx.send(
            f"This user does not have enough {settings.currency_display_plural(ctx.bot)} to remove "
            f"(balance={format_currency(player.yen, shortened=False, bot=ctx.bot)}).",
            ephemeral=True,
        )
        return
    formatted = format_currency(amount, shortened=False, bot=ctx.bot)
    await ctx.send(f"Removed {formatted} from {user.mention}.", ephemeral=True)
    log.info(f"{ctx.author} ({ctx.author.id}) removed {formatted} from {user} ({user.id})", extra={"webhook": True})


@yen.command()
@checks.has_permissions("kny_models.change_player")
async def set(ctx: commands.Context[knyDexBot], user: discord.User, amount: int):
    """
    Set the balance of the user provided

    Parameters
    ----------
    user: discord.User
        The user you want to set the balance of.
    amount: int
        The amount of coins to set.
    """
    player = await Player.objects.aget_or_none(discord_id=user.id)
    if not player:
        await ctx.send(f"This user has does not have a {settings.bot_name} account.", ephemeral=True)
        return

    if amount < 0:
        await ctx.send("The amount must be greater than or equal to zero.", ephemeral=True)
        return

    player.yen = amount
    await player.asave(update_fields=("yen",))
    formatted = format_currency(amount, shortened=False, bot=ctx.bot)
    await ctx.send(f"{user.mention} now has {formatted}.", ephemeral=True)
    log.info(
        f"{ctx.author} ({ctx.author.id}) set the balance of {user} ({user.id}) to {formatted}", extra={"webhook": True}
    )


@yen.command()
@checks.is_superuser()
async def setdefault(ctx: commands.Context[knyDexBot], amount: int, force: bool = False):
    """
    Set the default amount of currency provided to new users.

    Parameters
    ----------
    amount: int
        The new default amount to set.
    force: bool
        If true, then ALL users will have their balance reset to the default!
    """
    view = ConfirmChoiceView(ctx)
    msg = f"You are about to set the new default balance to {format_currency(amount, shortened=False, bot=ctx.bot)}.\n"
    if force:
        msg += (
            ":warning: You have chosen to reset ALL PLAYERS balance and set it to the new amount. "
            "This operation cannot be undone, all existing balances will be lost.\n"
        )
    msg += "\nDo you want to continue?"
    await ctx.send(msg, view=view)
    await view.wait()
    if not view.value:
        return

    @sync_to_async
    def wrapper():
        with connection.cursor() as cursor:
            cursor.execute(f"ALTER TABLE player ALTER COLUMN yen SET DEFAULT {int(amount)}")

    await wrapper()
    if force:
        await Player.objects.all().aupdate(yen=amount)

    await ctx.send("New default set.")
