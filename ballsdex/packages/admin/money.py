import logging

import discord
from discord.ext import commands

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.utils import checks
from bd_models.models import Player
from settings.models import settings

log = logging.getLogger(__name__)


@commands.hybrid_group()
@checks.has_permissions("bd_models.view_player")
async def money(ctx: commands.Context[BallsDexBot]):
    """
    Currency management tools
    """
    await ctx.send_help(ctx.command)


@money.command()
async def balance(ctx: commands.Context[BallsDexBot], user: discord.User):
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

    await ctx.send(f"{user.mention} currently has {player.money:,} coins.", ephemeral=True)


@money.command()
@checks.has_permissions("bd_models.change_player")
async def add(ctx: commands.Context[BallsDexBot], user: discord.User, amount: int):
    """
    Add coins to the user provided

    Parameters
    ----------
    user: discord.User
        The user you want to add coins to.
    amount: int
        The amount of coins to add.
    """
    player = await Player.objects.aget_or_none(discord_id=user.id)
    if not player:
        await ctx.send(f"This user does not have a {settings.bot_name} account.", ephemeral=True)
        return

    if amount <= 0:
        await ctx.send("The amount must be greater than zero.", ephemeral=True)
        return

    await player.add_money(amount)
    await ctx.send(f"{amount:,} coins have been added to {user.mention}.", ephemeral=True)
    log.info(f"{ctx.author} ({ctx.author.id}) added {amount:,} coins to {user} ({user.id})", extra={"webhook": True})


@money.command()
@checks.has_permissions("bd_models.change_player")
async def remove(ctx: commands.Context[BallsDexBot], user: discord.User, amount: int):
    """
    Remove coins from the user provided

    Parameters
    ----------
    user: discord.User
        The user you want to remove coins from.
    amount: int
        The amount of coins to remove.
    """
    player = await Player.objects.aget_or_none(discord_id=user.id)
    if not player:
        await ctx.send(f"This user does not have a {settings.bot_name} account.", ephemeral=True)
        return

    if amount <= 0:
        await ctx.send("The amount must be greater than zero.", ephemeral=True)
        return
    if not player.can_afford(amount):
        await ctx.send(f"This user does not have enough coins to remove (balance={player.money:,}).", ephemeral=True)
        return
    await player.remove_money(amount)
    await ctx.send(f"{amount:,} coins have been removed from {user.mention}.", ephemeral=True)
    log.info(
        f"{ctx.author} ({ctx.author.id}) removed {amount:,} coins from {user} ({user.id})", extra={"webhook": True}
    )


@money.command()
@checks.has_permissions("bd_models.change_player")
async def set(ctx: commands.Context[BallsDexBot], user: discord.User, amount: int):
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

    player.money = amount
    await player.asave()
    await ctx.send(f"{user.mention} now has {amount:,} coins.", ephemeral=True)
    log.info(
        f"{ctx.author} ({ctx.author.id}) set the balance of {user} ({user.id}) to {amount:,} coins",
        extra={"webhook": True},
    )
