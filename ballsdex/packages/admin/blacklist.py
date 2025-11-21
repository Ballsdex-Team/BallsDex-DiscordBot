import discord
from discord.ext import commands
from discord.utils import format_dt
from django.db import IntegrityError
from django.urls import reverse

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.utils import checks
from ballsdex.core.utils.logging import log_action
from ballsdex.core.utils.menus import Menu, ModelSource
from bd_models.models import BlacklistedGuild, BlacklistedID, BlacklistHistory, GuildConfig, Player

from .menu import BlacklistHistoryFormatter


@commands.hybrid_group()
@checks.has_permissions("bd_models.view_blacklistedid")
async def blacklist(ctx: commands.Context[BallsDexBot]):
    """
    Bot blacklist management
    """
    await ctx.send_help(ctx.command)


@blacklist.command(name="add")
@checks.has_permissions("bd_models.add_blacklistedid")
async def blacklist_add(ctx: commands.Context[BallsDexBot], user: discord.User, *, reason: str | None = None):
    """
    Add a user to the blacklist. No reload is needed.

    Parameters
    ----------
    user: discord.User
        The user you want to blacklist, if available in the current server.
    reason: str | None
        The reason for blacklisting the user.
    """
    if user == ctx.author:
        await ctx.send("You cannot blacklist yourself!", ephemeral=True)
        return

    try:
        await BlacklistedID.objects.acreate(discord_id=user.id, reason=reason, moderator_id=ctx.author.id)
        await BlacklistHistory.objects.acreate(
            discord_id=user.id, reason=reason, moderator_id=ctx.author.id, id_type="user"
        )
    except IntegrityError:
        await ctx.send("That user was already blacklisted.", ephemeral=True)
    else:
        ctx.bot.blacklist.add(user.id)
        await ctx.send("User is now blacklisted.", ephemeral=True)
        await log_action(f"{ctx.author} blacklisted {user} ({user.id}) for the following reason: {reason}.", ctx.bot)


@blacklist.command(name="remove")
@checks.has_permissions("bd_models.delete_blacklistedid")
async def blacklist_remove(ctx: commands.Context[BallsDexBot], user: discord.User, *, reason: str | None = None):
    """
    Remove a user from the blacklist. No reload is needed.

    Parameters
    ----------
    user: discord.User
        The user you want to unblacklist, if available in the current server.
    reason: str | None
        The reason for unblacklisting the user.
    """
    try:
        blacklisted = await BlacklistedID.objects.aget(discord_id=user.id)
    except BlacklistedID.DoesNotExist:
        await ctx.send("That user isn't blacklisted.", ephemeral=True)
    else:
        await blacklisted.adelete()
        await BlacklistHistory.objects.acreate(
            discord_id=user.id, reason=reason, moderator_id=ctx.author.id, id_type="user", action_type="unblacklist"
        )
        ctx.bot.blacklist.remove(user.id)
        await ctx.send("User is now removed from blacklist.", ephemeral=True)
        await log_action(f"{ctx.author} removed blacklist for user {user} ({user.id}).\nReason: {reason}", ctx.bot)


@blacklist.command(name="info")
async def blacklist_info(ctx: commands.Context[BallsDexBot], user: discord.User):
    """
    Check if a user is blacklisted and show the corresponding reason.

    Parameters
    ----------
    user: discord.User
        The user you want to check, if available in the current server.
    """
    try:
        blacklisted = await BlacklistedID.objects.aget(discord_id=user.id)
    except BlacklistedID.DoesNotExist:
        await ctx.send("That user isn't blacklisted.", ephemeral=True)
    else:
        if blacklisted.moderator_id:
            moderator_msg = (
                f"Moderator: {await ctx.bot.fetch_user(blacklisted.moderator_id)} ({blacklisted.moderator_id})"
            )
        else:
            moderator_msg = "Moderator: Unknown"
        if player := await Player.objects.aget_or_none(discord_id=user.id):
            admin_url = f"\n[View history online](<{reverse('admin:bd_models_player_change', args=(player.pk,))}>)"
        else:
            admin_url = ""
        if blacklisted.date:
            await ctx.send(
                f"`{user}` (`{user.id}`) was blacklisted on {format_dt(blacklisted.date)}"
                f"({format_dt(blacklisted.date, style='R')}) for the following reason:\n"
                f"{blacklisted.reason}\n{moderator_msg}{admin_url}",
                ephemeral=True,
            )
        else:
            if blacklisted.moderator_id:
                moderator_msg = (
                    f"Moderator: {await ctx.bot.fetch_user(blacklisted.moderator_id)} ({blacklisted.moderator_id})"
                )
            else:
                moderator_msg = "Moderator: Unknown"
            if player := await Player.objects.aget_or_none(discord_id=user.id):
                admin_url = f"\n[View history online](<{reverse('admin:bd_models_player_change', args=(player.pk,))}>)"
            else:
                admin_url = ""
            if blacklisted.date:
                await ctx.send(
                    f"`{user}` (`{user.id}`) was blacklisted on {format_dt(blacklisted.date)}"
                    f"({format_dt(blacklisted.date, style='R')}) for the following reason:\n"
                    f"{blacklisted.reason}\n{moderator_msg}{admin_url}",
                    ephemeral=True,
                )
            else:
                await ctx.send(
                    f"`{user}` (`{user.id}`) is currently blacklisted (date unknown)"
                    " for the following reason:\n"
                    f"{blacklisted.reason}\n{moderator_msg}{admin_url}",
                    ephemeral=True,
                )


@blacklist.command(name="history")
@checks.has_permissions("bd_models.view_blacklisthistory")
async def blacklist_history(ctx: commands.Context[BallsDexBot], user_id: str):
    """
    Show the history of a blacklisted user or guild.

    Parameters
    ----------
    id: str
        The ID of the user or guild you want to check.
    """
    try:
        _id = int(user_id)
    except ValueError:
        await ctx.send("The ID you gave is not valid.", ephemeral=True)
        return

    history = BlacklistHistory.objects.filter(discord_id=_id).order_by("-date")

    if not await history.aexists():
        await ctx.send("No history found for that ID.", ephemeral=True)
        return

    try:
        user = await ctx.bot.fetch_user(_id)
    except discord.NotFound:
        await ctx.send("User was not found from Discord.", ephemeral=True)
        return

    view = discord.ui.LayoutView()
    container = discord.ui.Container()
    view.add_item(container)
    menu = Menu(ctx.bot, view, ModelSource(history, per_page=1), BlacklistHistoryFormatter(container, user))
    await menu.init()
    await ctx.send(view=view, ephemeral=True)


@commands.hybrid_group()
@checks.has_permissions("bd_models.view_blacklistedguild")
async def blacklistguild(ctx: commands.Context[BallsDexBot]):
    """
    Guild blacklist management
    """
    await ctx.send_help(ctx.command)


@blacklistguild.command(name="add")
@checks.has_permissions("bd_models.add_blacklistedguild")
async def blacklist_add_guild(ctx: commands.Context[BallsDexBot], guild_id: str, *, reason: str):
    """
    Add a guild to the blacklist. No reload is needed.

    Parameters
    ----------
    guild_id: str
        The ID of the guild you want to blacklist.
    reason: str
        The reason for blacklisting the guild.
    """

    try:
        guild = await ctx.bot.fetch_guild(int(guild_id))
    except ValueError:
        await ctx.send("The guild ID you gave is not valid.", ephemeral=True)
        return
    except discord.NotFound:
        await ctx.send("The given guild ID could not be found.", ephemeral=True)
        return

    final_reason = f"{reason}\nBy: {ctx.author} ({ctx.author.id})"

    try:
        await BlacklistedGuild.objects.acreate(discord_id=guild.id, reason=final_reason, moderator_id=ctx.author.id)
        await BlacklistHistory.objects.acreate(
            discord_id=guild.id, reason=final_reason, moderator_id=ctx.author.id, id_type="guild"
        )
    except IntegrityError:
        await ctx.send("That guild was already blacklisted.", ephemeral=True)
    else:
        ctx.bot.blacklist_guild.add(guild.id)
        await ctx.send("Guild is now blacklisted.", ephemeral=True)
        await log_action(
            f"{ctx.author} blacklisted the guild {guild}({guild.id}) for the following reason: {reason}.", ctx.bot
        )


@blacklistguild.command(name="remove")
@checks.has_permissions("bd_models.delete_blacklistedguild")
async def blacklist_remove_guild(ctx: commands.Context[BallsDexBot], guild_id: str, *, reason: str | None = None):
    """
    Remove a guild from the blacklist. No reload is needed.

    Parameters
    ----------
    guild_id: str
        The ID of the guild you want to unblacklist.
    reason: str | None
        The reason for unblacklisting the guild.
    """

    try:
        guild = await ctx.bot.fetch_guild(int(guild_id))
    except ValueError:
        await ctx.send("The guild ID you gave is not valid.", ephemeral=True)
        return
    except discord.NotFound:
        await ctx.send("The given guild ID could not be found.", ephemeral=True)
        return

    try:
        blacklisted = await BlacklistedGuild.objects.aget(discord_id=guild.id)
    except BlacklistedGuild.DoesNotExist:
        await ctx.send("That guild isn't blacklisted.", ephemeral=True)
    else:
        await blacklisted.adelete()
        await BlacklistHistory.objects.acreate(
            discord_id=guild.id, reason=reason, moderator_id=ctx.author.id, id_type="guild", action_type="unblacklist"
        )
        ctx.bot.blacklist_guild.remove(guild.id)
        await ctx.send("Guild is now removed from blacklist.", ephemeral=True)
        await log_action(f"{ctx.author} removed blacklist for guild {guild} ({guild.id}).\nReason: {reason}", ctx.bot)


@blacklistguild.command(name="info")
async def blacklist_info_guild(ctx: commands.Context[BallsDexBot], guild_id: str):
    """
    Check if a guild is blacklisted and show the corresponding reason.

    Parameters
    ----------
    guild_id: str
        The ID of the guild you want to check.
    """

    try:
        guild = await ctx.bot.fetch_guild(int(guild_id))
    except ValueError:
        await ctx.send("The guild ID you gave is not valid.", ephemeral=True)
        return
    except discord.NotFound:
        await ctx.send("The given guild ID could not be found.", ephemeral=True)
        return

    try:
        blacklisted = await BlacklistedGuild.objects.aget(discord_id=guild.id)
    except BlacklistedGuild.DoesNotExist:
        await ctx.send("That guild isn't blacklisted.", ephemeral=True)
    else:
        if blacklisted.moderator_id:
            moderator_msg = (
                f"Moderator: {await ctx.bot.fetch_user(blacklisted.moderator_id)}({blacklisted.moderator_id})"
            )
        else:
            moderator_msg = "Moderator: Unknown"
        if gconf := await GuildConfig.objects.aget_or_none(guild_id=guild.id):
            admin_url = f"\n[View history online](<{reverse('admin:bd_models_guildconfig_change', args=(gconf.pk,))}>)"
        else:
            admin_url = ""
        if blacklisted.date:
            await ctx.send(
                f"`{guild}` (`{guild.id}`) was blacklisted on {format_dt(blacklisted.date)}"
                f"({format_dt(blacklisted.date, style='R')}) for the following reason:\n"
                f"{blacklisted.reason}\n{moderator_msg}{admin_url}",
                ephemeral=True,
            )
        else:
            await ctx.send(
                f"`{guild}` (`{guild.id}`) is currently blacklisted (date unknown)"
                " for the following reason:\n"
                f"{blacklisted.reason}\n{moderator_msg}{admin_url}",
                ephemeral=True,
            )
