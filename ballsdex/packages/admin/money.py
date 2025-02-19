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
    async def balance(
        self,
        interaction: discord.Interaction[BallsDexBot],
        user: discord.User
    ):
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
                f"This user has does not have a {settings.bot_name} account.", ephemeral=True
            )
            return

        await interaction.followup.send(
            f"{user.mention} currently has {player.money:,} coins.", ephemeral=True
        )

    @app_commands.command()
    async def add(
        self,
        interaction: discord.Interaction[BallsDexBot],
        user: discord.User,
        amount: int
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
                f"This user has does not have a {settings.bot_name} account.", ephemeral=True
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

    @app_commands.command()
    async def remove(
        self,
        interaction: discord.Interaction[BallsDexBot],
        user: discord.User,
        amount: int
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
                f"This user has does not have a {settings.bot_name} account.", ephemeral=True
            )
            return

        if amount <= 0:
            await interaction.followup.send(
                "The amount must be greater than zero.", ephemeral=True
            )
            return
        if not await player.can_afford(amount):
            await interaction.followup.send(
                "This user does not have enough coins to remove.", ephemeral=True
            )
            return
        await player.remove_money(amount)
        await interaction.followup.send(
            f"{amount:,} coins have been removed from {user.mention}.", ephemeral=True
        )

    @app_commands.command()
    async def set(
        self,
        interaction: discord.Interaction[BallsDexBot],
        user: discord.User,
        amount: int
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