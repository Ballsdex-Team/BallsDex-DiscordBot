import discord
from discord import app_commands

from ballsdex.core.bot import BallsDexBot
from ballsdex.settings import settings


class Logs(app_commands.Group):
    """
    Bot logs management
    """

    @app_commands.command(name="catchlogs")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def logs_add(
        self,
        interaction: discord.Interaction[BallsDexBot],
        user: discord.User,
    ):
        """
        Add or remove a user from catch logs.

        Parameters
        ----------
        user: discord.User
            The user you want to add or remove to the logs.
        """
        if user.id in interaction.client.catch_log:
            interaction.client.catch_log.remove(user.id)
            await interaction.response.send_message(
                f"{user} removed from catch logs.", ephemeral=True
            )
        else:
            interaction.client.catch_log.add(user.id)
            await interaction.response.send_message(f"{user} added to catch logs.", ephemeral=True)

    @app_commands.command(name="commandlogs")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def commandlogs_add(
        self,
        interaction: discord.Interaction[BallsDexBot],
        user: discord.User,
    ):
        """
        Add or remove a user from command logs.

        Parameters
        ----------
        user: discord.User
            The user you want to add or remove to the logs.
        """
        if user.id in interaction.client.command_log:
            interaction.client.command_log.remove(user.id)
            await interaction.response.send_message(
                f"{user} removed from command logs.", ephemeral=True
            )
        else:
            interaction.client.command_log.add(user.id)
            await interaction.response.send_message(
                f"{user} added to command logs.", ephemeral=True
            )
