import discord
from discord import app_commands

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.models import Player
from ballsdex.core.utils.logging import log_action
from ballsdex.settings import settings


class Money(app_commands.Group):
    """
    Commands to manipulate user's currency.
    """

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def balance(self, interaction: discord.Interaction[BallsDexBot], user: discord.User):
        """
        Show the balance of the user provided

        Parameters
        ----------
        user: discord.User
            The user you want to get information about.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        player = await Player.get_or_none(discord_id=user.id)
        if not player:
            await interaction.followup.send(
                f"This user does not have a {settings.bot_name} account.", ephemeral=True
            )
            return

        await interaction.followup.send(
            f"{user.mention} currently has {player.money:,} coins.", ephemeral=True
        )

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def add(
        self, interaction: discord.Interaction[BallsDexBot], user: discord.User, amount: int
    ):
        """
        Add coins to the user provided

        Parameters
        ----------
        user: discord.User
            The user you want to add coins to.
        amount: int
            The amount of coins to add.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        player = await Player.get_or_none(discord_id=user.id)
        if not player:
            await interaction.followup.send(
                f"This user does not have a {settings.bot_name} account.", ephemeral=True
            )
            return

        if amount <= 0:
            await interaction.followup.send(
                "The amount must be greater than zero.", ephemeral=True
            )
            return

        await player.add_money(amount)
        await interaction.followup.send(
            f"{amount:,} coins have been added to {user.mention}.", ephemeral=True
        )
        await log_action(
            f"{interaction.user} ({interaction.user.id}) added {amount:,} coins to "
            f"{user} ({user.id})",
            interaction.client,
        )

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def remove(
        self, interaction: discord.Interaction[BallsDexBot], user: discord.User, amount: int
    ):
        """
        Remove coins from the user provided

        Parameters
        ----------
        user: discord.User
            The user you want to remove coins from.
        amount: int
            The amount of coins to remove.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        player = await Player.get_or_none(discord_id=user.id)
        if not player:
            await interaction.followup.send(
                f"This user does not have a {settings.bot_name} account.", ephemeral=True
            )
            return

        if amount <= 0:
            await interaction.followup.send(
                "The amount must be greater than zero.", ephemeral=True
            )
            return
        if not player.can_afford(amount):
            await interaction.followup.send(
                f"This user does not have enough coins to remove (balance={player.balance}).", ephemeral=True
            )
            return
        await player.remove_money(amount)
        await interaction.followup.send(
            f"{amount:,} coins have been removed from {user.mention}.", ephemeral=True
        )
        await log_action(
            f"{interaction.user} ({interaction.user.id}) removed {amount:,} coins from "
            f"{user} ({user.id})",
            interaction.client,
        )

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def set(
        self, interaction: discord.Interaction[BallsDexBot], user: discord.User, amount: int
    ):
        """
        Set the balance of the user provided

        Parameters
        ----------
        user: discord.User
            The user you want to set the balance of.
        amount: int
            The amount of coins to set.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        player = await Player.get_or_none(discord_id=user.id)
        if not player:
            await interaction.followup.send(
                f"This user has does not have a {settings.bot_name} account.", ephemeral=True
            )
            return

        if amount < 0:
            await interaction.followup.send(
                "The amount must be greater than or equal to zero.", ephemeral=True
            )
            return

        player.money = amount
        await player.save()
        await interaction.followup.send(
            f"{user.mention} now has {amount:,} coins.", ephemeral=True
        )
        await log_action(
            f"{interaction.user} ({interaction.user.id}) set the balance of "
            f"{user} ({user.id}) to {amount:,} coins",
            interaction.client,
        )
