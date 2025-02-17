import discord
from discord import app_commands

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.models import Player
from ballsdex.core.utils.logging import log_action
from ballsdex.settings import settings


class Coins(app_commands.Group):
    """
    Commands to manipulate user's coins.
    """

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def add(
        self,
        interaction: discord.Interaction[BallsDexBot],
        user: discord.User | None = None,
        user_id: str | None = None,
        amount: int = 0,
    ):
        """
        Add coins to a user.

        Parameters
        ----------
        user: discord.User | None
            The user you want to add coins to.
        user_id: str | None
            The ID of the user you want to add coins to.
        amount: int
            The number of coins to add.
        """
        if (user is None and user_id is None) or (user is not None and user_id is not None):
            await interaction.response.send_message(
                "You must provide either `user` or `user_id`", ephemeral=True
            )
            return

        if amount < 0:
            await interaction.response.send_message(
                f"The amount of {settings.currency_name} " "to add cannot be negative.",
                ephemeral=True,
            )
            return

        if user_id is not None:
            try:
                user = await interaction.client.fetch_user(int(user_id))
            except ValueError:
                await interaction.response.send_message(
                    "The user ID you provided is not valid.", ephemeral=True
                )
                return
            except discord.NotFound:
                await interaction.response.send_message(
                    "The given user ID could not be found.", ephemeral=True
                )
                return

        assert user
        player, created = await Player.get_or_create(discord_id=user.id)
        await player.add_coins(amount)
        await interaction.response.send_message(
            f"Added {amount} {settings.currency_name} to {user.name}.", ephemeral=True
        )

        await log_action(
            f"{interaction.user} added {amount} {settings.currency_name} "
            f"to {user.name} ({user.id}).",
            interaction.client,
        )

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def remove(
        self,
        interaction: discord.Interaction[BallsDexBot],
        user: discord.User | None = None,
        user_id: str | None = None,
        amount: int = 0,
    ):
        """
        Remove coins from a user.

        Parameters
        ----------
        user: discord.User | None
            The user you want to remove coins from.
        user_id: str | None
            The ID of the user you want to remove coins from.
        amount: int
            The number of coins to remove.
        """
        if (user is None and user_id is None) or (user is not None and user_id is not None):
            await interaction.response.send_message(
                "You must provide either `user` or `user_id`", ephemeral=True
            )
            return

        if amount < 0:
            await interaction.response.send_message(
                f"The amount of {settings.currency_name} " "to remove cannot be negative.",
                ephemeral=True,
            )
            return

        if user_id is not None:
            try:
                user = await interaction.client.fetch_user(int(user_id))
            except ValueError:
                await interaction.response.send_message(
                    "The user ID you provided is not valid.", ephemeral=True
                )
                return
            except discord.NotFound:
                await interaction.response.send_message(
                    "The given user ID could not be found.", ephemeral=True
                )
                return

        assert user
        player, created = await Player.get_or_create(discord_id=user.id)
        await player.remove_coins(amount)
        await interaction.response.send_message(
            f"Removed {amount} {settings.currency_name} to {user.name}.", ephemeral=True
        )

        await log_action(
            f"{interaction.user} removed {amount} {settings.currency_name} "
            f"to {user.name} ({user.id}).",
            interaction.client,
        )
