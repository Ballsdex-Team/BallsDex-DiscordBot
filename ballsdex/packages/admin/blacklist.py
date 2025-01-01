import discord
from discord import app_commands
from discord.utils import format_dt
from tortoise.exceptions import DoesNotExist, IntegrityError

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.models import BlacklistedGuild, BlacklistedID, BlacklistHistory
from ballsdex.core.utils.logging import log_action
from ballsdex.core.utils.paginator import Pages
from ballsdex.packages.admin.menu import BlacklistViewFormat
from ballsdex.settings import settings


class Blacklist(app_commands.Group):
    """
    Bot blacklist management
    """

    @app_commands.command(name="add")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def blacklist_add(
        self,
        interaction: discord.Interaction[BallsDexBot],
        user: discord.User,
        reason: str | None = None,
    ):
        """
        Add a user to the blacklist. No reload is needed.

        Parameters
        ----------
        user: discord.User
            The user you want to blacklist, if available in the current server.
        reason: str | None
        """
        if user == interaction.user:
            await interaction.response.send_message(
                "You cannot blacklist yourself!", ephemeral=True
            )
            return

        try:
            await BlacklistedID.create(
                discord_id=user.id, reason=reason, moderator_id=interaction.user.id
            )
            await BlacklistHistory.create(
                discord_id=user.id, reason=reason, moderator_id=interaction.user.id, id_type="user"
            )
        except IntegrityError:
            await interaction.response.send_message(
                "That user was already blacklisted.", ephemeral=True
            )
        else:
            interaction.client.blacklist.add(user.id)
            await interaction.response.send_message("User is now blacklisted.", ephemeral=True)
        await log_action(
            f"{interaction.user} blacklisted {user} ({user.id})"
            f" for the following reason: {reason}.",
            interaction.client,
        )

    @app_commands.command(name="remove")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def blacklist_remove(
        self,
        interaction: discord.Interaction[BallsDexBot],
        user: discord.User,
        reason: str | None = None,
    ):
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
            blacklisted = await BlacklistedID.get(discord_id=user.id)
        except DoesNotExist:
            await interaction.response.send_message("That user isn't blacklisted.", ephemeral=True)
        else:
            await blacklisted.delete()
            await BlacklistHistory.create(
                discord_id=user.id,
                reason=reason,
                moderator_id=interaction.user.id,
                id_type="user",
                action_type="unblacklist",
            )
            interaction.client.blacklist.remove(user.id)
            await interaction.response.send_message(
                "User is now removed from blacklist.", ephemeral=True
            )
        await log_action(
            f"{interaction.user} removed blacklist for user {user} ({user.id}).\nReason: {reason}",
            interaction.client,
        )

    @app_commands.command(name="info")
    async def blacklist_info(
        self, interaction: discord.Interaction[BallsDexBot], user: discord.User
    ):
        """
        Check if a user is blacklisted and show the corresponding reason.

        Parameters
        ----------
        user: discord.User
            The user you want to check, if available in the current server.
        """
        try:
            blacklisted = await BlacklistedID.get(discord_id=user.id)
        except DoesNotExist:
            await interaction.response.send_message("That user isn't blacklisted.", ephemeral=True)
        else:
            if blacklisted.moderator_id:
                moderator_msg = (
                    f"Moderator: {await interaction.client.fetch_user(blacklisted.moderator_id)}"
                    f" ({blacklisted.moderator_id})"
                )
            else:
                moderator_msg = "Moderator: Unknown"
            if blacklisted.date:
                await interaction.response.send_message(
                    f"`{user}` (`{user.id}`) was blacklisted on {format_dt(blacklisted.date)}"
                    f"({format_dt(blacklisted.date, style='R')}) for the following reason:\n"
                    f"{blacklisted.reason}\n{moderator_msg}",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"`{user}` (`{user.id}`) is currently blacklisted (date unknown)"
                    " for the following reason:\n"
                    f"{blacklisted.reason}\n{moderator_msg}",
                    ephemeral=True,
                )

    @app_commands.command(name="history")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def blacklist_history(self, interaction: discord.Interaction[BallsDexBot], user_id: str):
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
            await interaction.response.send_message(
                "The ID you gave is not valid.", ephemeral=True
            )
            return

        history = await BlacklistHistory.filter(discord_id=_id).order_by("-date")

        if not history:
            await interaction.response.send_message(
                "No history found for that ID.", ephemeral=True
            )
            return

        source = BlacklistViewFormat(history, _id, interaction.client)
        pages = Pages(source=source, interaction=interaction, compact=True)  # type: ignore
        await pages.start(ephemeral=True)


class BlacklistGuild(app_commands.Group):
    """
    Guild blacklist management
    """

    @app_commands.command(name="add")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def blacklist_add_guild(
        self,
        interaction: discord.Interaction[BallsDexBot],
        guild_id: str,
        reason: str,
    ):
        """
        Add a guild to the blacklist. No reload is needed.

        Parameters
        ----------
        guild_id: str
            The ID of the guild you want to blacklist.
        reason: str
        """

        try:
            guild = await interaction.client.fetch_guild(int(guild_id))  # type: ignore
        except ValueError:
            await interaction.response.send_message(
                "The guild ID you gave is not valid.", ephemeral=True
            )
            return
        except discord.NotFound:
            await interaction.response.send_message(
                "The given guild ID could not be found.", ephemeral=True
            )
            return

        final_reason = f"{reason}\nBy: {interaction.user} ({interaction.user.id})"

        try:
            await BlacklistedGuild.create(
                discord_id=guild.id, reason=final_reason, moderator_id=interaction.user.id
            )
            await BlacklistHistory.create(
                discord_id=guild.id,
                reason=final_reason,
                moderator_id=interaction.user.id,
                id_type="guild",
            )
        except IntegrityError:
            await interaction.response.send_message(
                "That guild was already blacklisted.", ephemeral=True
            )
        else:
            interaction.client.blacklist_guild.add(guild.id)
            await interaction.response.send_message("Guild is now blacklisted.", ephemeral=True)
        await log_action(
            f"{interaction.user} blacklisted the guild {guild}({guild.id}) "
            f"for the following reason: {reason}.",
            interaction.client,
        )

    @app_commands.command(name="remove")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def blacklist_remove_guild(
        self,
        interaction: discord.Interaction[BallsDexBot],
        guild_id: str,
        reason: str | None = None,
    ):
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
            guild = await interaction.client.fetch_guild(int(guild_id))  # type: ignore
        except ValueError:
            await interaction.response.send_message(
                "The guild ID you gave is not valid.", ephemeral=True
            )
            return
        except discord.NotFound:
            await interaction.response.send_message(
                "The given guild ID could not be found.", ephemeral=True
            )
            return

        try:
            blacklisted = await BlacklistedGuild.get(discord_id=guild.id)
        except DoesNotExist:
            await interaction.response.send_message(
                "That guild isn't blacklisted.", ephemeral=True
            )
        else:
            await blacklisted.delete()
            await BlacklistHistory.create(
                discord_id=guild.id,
                reason=reason,
                moderator_id=interaction.user.id,
                id_type="guild",
                action_type="unblacklist",
            )
            interaction.client.blacklist_guild.remove(guild.id)
            await interaction.response.send_message(
                "Guild is now removed from blacklist.", ephemeral=True
            )
            await log_action(
                f"{interaction.user} removed blacklist for guild {guild} ({guild.id}).\n"
                f"Reason: {reason}",
                interaction.client,
            )

    @app_commands.command(name="info")
    async def blacklist_info_guild(
        self,
        interaction: discord.Interaction[BallsDexBot],
        guild_id: str,
    ):
        """
        Check if a guild is blacklisted and show the corresponding reason.

        Parameters
        ----------
        guild_id: str
            The ID of the guild you want to check.
        """

        try:
            guild = await interaction.client.fetch_guild(int(guild_id))  # type: ignore
        except ValueError:
            await interaction.response.send_message(
                "The guild ID you gave is not valid.", ephemeral=True
            )
            return
        except discord.NotFound:
            await interaction.response.send_message(
                "The given guild ID could not be found.", ephemeral=True
            )
            return

        try:
            blacklisted = await BlacklistedGuild.get(discord_id=guild.id)
        except DoesNotExist:
            await interaction.response.send_message(
                "That guild isn't blacklisted.", ephemeral=True
            )
        else:
            if blacklisted.moderator_id:
                moderator_msg = (
                    f"Moderator: {await interaction.client.fetch_user(blacklisted.moderator_id)}"
                    f"({blacklisted.moderator_id})"
                )
            else:
                moderator_msg = "Moderator: Unknown"
            if blacklisted.date:
                await interaction.response.send_message(
                    f"`{guild}` (`{guild.id}`) was blacklisted on {format_dt(blacklisted.date)}"
                    f"({format_dt(blacklisted.date, style='R')}) for the following reason:\n"
                    f"{blacklisted.reason}\n{moderator_msg}",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"`{guild}` (`{guild.id}`) is currently blacklisted (date unknown)"
                    " for the following reason:\n"
                    f"{blacklisted.reason}\n{moderator_msg}",
                    ephemeral=True,
                )
